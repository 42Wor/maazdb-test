import sys
import subprocess
import time
import re
import os
import sqlite3
import hashlib
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPlainTextEdit, QToolBar, QDockWidget, QComboBox,
    QListWidget, QFileDialog, QTabWidget, QTextEdit, QMessageBox,
    QDialog, QPushButton, QLabel, QHBoxLayout, QMenu, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QFont, QAction, QPainter, QColor, QPen

# Try importing pyqtgraph for the charts
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

# ==========================================
# DATABASE MANAGER (EFFICIENT STORAGE)
# ==========================================
class DBManager:
    def __init__(self, workspace_dir):
        self.db_path = os.path.join(workspace_dir, "test_history.db")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_name TEXT,
                first_run_timestamp DATETIME,
                last_run_timestamp DATETIME,
                run_count INTEGER,
                duration REAL,
                status TEXT,
                output_hash TEXT,
                output_text BLOB
            )
        ''')
        self.conn.commit()

    def save_result(self, run_name, duration, status, output_text):
        # 1. Hash the output for deduplication
        output_hash = hashlib.sha256(output_text.encode('utf-8')).hexdigest()
        
        cursor = self.conn.cursor()
        # 2. Get the most recent run for this specific test
        cursor.execute('''
            SELECT id, output_hash, run_count FROM test_results 
            WHERE run_name = ? ORDER BY last_run_timestamp DESC LIMIT 1
        ''', (run_name,))
        row = cursor.fetchone()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 3. Deduplication Logic
        if row and row[1] == output_hash:
            # Output is identical to the last run. Just update timestamp and count!
            record_id = row[0]
            new_count = row[2] + 1
            cursor.execute('''
                UPDATE test_results 
                SET last_run_timestamp = ?, run_count = ?, duration = ?, status = ?
                WHERE id = ?
            ''', (now, new_count, duration, status, record_id))
        else:
            # Output is new. Compress it and save as a new row.
            compressed_out = zlib.compress(output_text.encode('utf-8'))
            cursor.execute('''
                INSERT INTO test_results 
                (run_name, first_run_timestamp, last_run_timestamp, run_count, duration, status, output_hash, output_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (run_name, now, now, 1, duration, status, output_hash, compressed_out))
        
        self.conn.commit()

# ==========================================
# STARTUP POPUP: WORKSPACE SELECTION
# ==========================================
class WorkspaceDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Select Workspace")
        self.setFixedSize(400, 150)
        self.workspace_path = ""

        layout = QVBoxLayout()
        label = QLabel("Please select or create a workspace folder for your tests and database:")
        label.setWordWrap(True)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        self.btn_choose = QPushButton("📂 Choose / Create Folder")
        self.btn_choose.clicked.connect(self.choose_folder)
        btn_layout.addWidget(self.btn_choose)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Workspace Directory")
        if folder:
            self.workspace_path = folder
            self.accept()

# ==========================================
# THREAD: INDIVIDUAL TEST RUNNER
# ==========================================
class TestRunnerThread(QThread):
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(str)

    def __init__(self, tab_id, run_data, db_manager):
        super().__init__()
        self.tab_id = tab_id
        self.run_data = run_data
        self.db = db_manager
        self.running = True
        self.process = None
        self.full_output = []

    def emit_and_store(self, msg):
        self.log_signal.emit(self.tab_id, msg)
        self.full_output.append(msg)

    def run(self):
        name = self.run_data.get('name', 'Unknown')
        
        if 'file' in self.run_data:
            filepath = Path(self.run_data['file'])
            cwd = str(filepath.parent)
            filename = filepath.name
            ext = filepath.suffix.lower()

            if ext == '.py': cmd = f'python "{filename}"'
            elif ext == '.js': cmd = f'node "{filename}"'
            elif ext == '.sh': cmd = f'bash "{filename}"'
            elif ext == '.bat': cmd = f'"{filename}"'
            else: cmd = f'"{filename}"'
        else:
            cmd = self.run_data.get('cmd', '')
            cwd = self.run_data.get('dir', './')

        self.emit_and_store(f"▶ OPENING RUN: {name}")
        self.emit_and_store(f"▶ CMD: {cmd}\n{'-'*40}")
        
        start_time = time.time()
        status = "Pass"
        
        try:
            self.process = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=True, encoding="utf-8", errors="replace"
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.running:
                    self.process.terminate()
                    status = "Fail"
                    break
                self.emit_and_store(line.strip())

            self.process.wait()
            if self.process.returncode != 0:
                status = "Fail"
                
            duration = time.time() - start_time
            self.emit_and_store(f"\n{'-'*40}\n✔ FINISHED in {duration:.2f}s (Status: {status})")

        except Exception as e:
            self.emit_and_store(f"\n❌ ERROR: {str(e)}")
            duration = time.time() - start_time
            status = "Fail"

        # Save to SQLite Database
        output_text = "\n".join(self.full_output)
        self.db.save_result(name, duration, status, output_text)
        
        self.finished_signal.emit(self.tab_id)

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()

# ==========================================
# GITHUB-STYLE HEATMAP WIDGET
# ==========================================
class HeatmapWidget(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.setMinimumHeight(150)
        self.data = {}
        self.load_data()

    def load_data(self):
        cursor = self.db.conn.cursor()
        # Group runs by date. Count total runs, and count how many failed.
        cursor.execute('''
            SELECT date(last_run_timestamp), SUM(run_count), 
                   SUM(CASE WHEN status='Fail' THEN 1 ELSE 0 END)
            FROM test_results 
            GROUP BY date(last_run_timestamp)
        ''')
        rows = cursor.fetchall()
        self.data = {row[0]: {"total": row[1], "fails": row[2]} for row in rows}

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        box_size = 12
        margin = 2
        
        today = datetime.now().date()
        start_date = today - timedelta(days=365)
        
        # Draw 52 weeks (columns) x 7 days (rows)
        for i in range(365):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            
            col = i // 7
            row = i % 7
            
            x = col * (box_size + margin) + 20
            y = row * (box_size + margin) + 20
            
            # Default color (Empty / No runs)
            color = QColor("#2d333b") 
            
            if date_str in self.data:
                stats = self.data[date_str]
                if stats["fails"] > 0:
                    # Red for failures (intensity based on total runs)
                    intensity = min(255, 100 + (stats["total"] * 20))
                    color = QColor(intensity, 50, 50)
                else:
                    # Green for passes
                    intensity = min(255, 100 + (stats["total"] * 20))
                    color = QColor(50, intensity, 50)
            
            painter.setBrush(color)
            painter.setPen(QPen(Qt.GlobalColor.transparent))
            painter.drawRoundedRect(QRectF(x, y, box_size, box_size), 2, 2)

# ==========================================
# ANALYTICS DASHBOARD WINDOW
# ==========================================
class AnalyticsWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.setWindowTitle("📊 Analytics & History Dashboard")
        self.resize(900, 600)
        
        central = QWidget()
        layout = QVBoxLayout(central)
        
        # 1. Heatmap Section
        layout.addWidget(QLabel("<b>Activity Heatmap (Last 365 Days)</b>"))
        self.heatmap = HeatmapWidget(self.db)
        layout.addWidget(self.heatmap)
        
        # 2. Graph Section
        layout.addWidget(QLabel("<b>Execution Time History</b>"))
        
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Select Test:"))
        self.combo_tests = QComboBox()
        self.populate_tests()
        self.combo_tests.currentTextChanged.connect(self.update_graph)
        controls.addWidget(self.combo_tests)
        controls.addStretch()
        layout.addLayout(controls)
        
        if HAS_PYQTGRAPH:
            self.plot_widget = pg.PlotWidget(background='#1e1e1e')
            self.plot_widget.setLabel('left', 'Duration (Seconds)')
            self.plot_widget.setLabel('bottom', 'Run Instance')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            layout.addWidget(self.plot_widget)
            self.update_graph(self.combo_tests.currentText())
        else:
            lbl = QLabel("⚠️ Please run 'pip install pyqtgraph' in your terminal to view execution graphs.")
            lbl.setStyleSheet("color: #ffcc00; font-size: 14px;")
            layout.addWidget(lbl)
            
        self.setCentralWidget(central)

    def populate_tests(self):
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT DISTINCT run_name FROM test_results")
        tests = [row[0] for row in cursor.fetchall()]
        self.combo_tests.addItems(tests)

    def update_graph(self, test_name):
        if not HAS_PYQTGRAPH or not test_name: return
        
        self.plot_widget.clear()
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT duration FROM test_results 
            WHERE run_name = ? ORDER BY last_run_timestamp ASC
        ''', (test_name,))
        
        durations = [row[0] for row in cursor.fetchall()]
        if durations:
            pen = pg.mkPen(color=(0, 255, 0), width=2)
            self.plot_widget.plot(range(len(durations)), durations, pen=pen, symbol='o', symbolBrush=(0,255,0))

# ==========================================
# MAIN GUI APPLICATION
# ==========================================
class ProTestIDE(QMainWindow):
    def __init__(self, workspace_dir):
        super().__init__()
        self.workspace_dir = workspace_dir
        self.db_manager = DBManager(workspace_dir)
        
        self.setWindowTitle(f"Shelf & Run Test IDE - Workspace: {self.workspace_dir}")
        self.resize(1200, 800)

        self.parsed_runs = {}
        self.active_threads = {}
        self.tab_counter = 0
        self.analytics_window = None

        self.init_ui()

    def init_ui(self):
        # --- TOOLBAR ---
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        btn_load = QAction("📂 Load Shelf", self)
        btn_load.triggered.connect(self.load_shelf)
        toolbar.addAction(btn_load)

        btn_save = QAction("💾 Save Shelf", self)
        btn_save.triggered.connect(self.save_shelf)
        toolbar.addAction(btn_save)

        toolbar.addSeparator()

        btn_add_file = QAction("➕ Add Run from File", self)
        btn_add_file.triggered.connect(self.auto_generate_run)
        toolbar.addAction(btn_add_file)

        toolbar.addSeparator()

        btn_run_sel = QAction("▶ Execute Selected", self)
        btn_run_sel.triggered.connect(self.execute_selected_run)
        toolbar.addAction(btn_run_sel)

        btn_run_all = QAction("⏭ Execute All", self)
        btn_run_all.triggered.connect(self.execute_all_runs)
        toolbar.addAction(btn_run_all)
        
        toolbar.addSeparator()
        
        btn_analytics = QAction("📊 Analytics Dashboard", self)
        btn_analytics.triggered.connect(self.open_analytics)
        toolbar.addAction(btn_analytics)

        # --- CENTRAL WIDGET (Code Editor) ---
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 11))
        self.editor.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self.show_context_menu)
        
        default_code = """# Welcome to your Shelf.
# Right-click to add a new run block, or use the toolbar!

run "Example Auto Test" {
    file: "C:/example/path/script.py"
}
"""
        self.editor.setPlainText(default_code)
        self.editor.textChanged.connect(self.parse_shelf)
        self.setCentralWidget(self.editor)

        # --- DOCK 1: SHELF EXPLORER (Left) ---
        self.dock_explorer = QDockWidget("Shelf Contents", self)
        self.run_list = QListWidget()
        self.run_list.setStyleSheet("background-color: #252526; color: #ffffff; font-size: 14px;")
        self.dock_explorer.setWidget(self.run_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_explorer)

        # --- DOCK 2: TERMINAL TABS (Bottom) ---
        self.dock_terminal = QDockWidget("Run Results", self)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.dock_terminal.setWidget(self.tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_terminal)

        self.parse_shelf()

    def open_analytics(self):
        self.analytics_window = AnalyticsWindow(self.db_manager)
        self.analytics_window.show()

    def show_context_menu(self, position):
        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()
        add_run_action = QAction("➕ Add New 'Run' Block", self)
        add_run_action.triggered.connect(self.insert_empty_run_block)
        menu.addAction(add_run_action)
        menu.exec(self.editor.mapToGlobal(position))

    def insert_empty_run_block(self):
        self.editor.insertPlainText('\nrun "New Test" {\n    file: "path/to/file.py"\n}\n')

    def auto_generate_run(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Script to Test", "", "All Files (*)")
        if file_path:
            run_name = Path(file_path).stem.replace("_", " ").title()
            self.editor.setPlainText(self.editor.toPlainText() + f'\nrun "{run_name}" {{\n    file: "{file_path}"\n}}\n')
            self.editor.verticalScrollBar().setValue(self.editor.verticalScrollBar().maximum())

    def parse_shelf(self):
        text = self.editor.toPlainText()
        self.parsed_runs = {}
        self.run_list.clear()

        block_pattern = re.compile(r'run\s+"([^"]+)"\s*\{([^}]+)\}')
        for match in block_pattern.finditer(text):
            name, body = match.group(1), match.group(2)
            file_m = re.search(r'file:\s*"([^"]+)"', body)
            cmd_m = re.search(r'cmd:\s*"([^"]+)"', body)
            dir_m = re.search(r'dir:\s*"([^"]+)"', body)

            run_data = {"name": name}
            if file_m: run_data["file"] = file_m.group(1)
            else:
                run_data["cmd"] = cmd_m.group(1) if cmd_m else ""
                run_data["dir"] = dir_m.group(1) if dir_m else "./"

            self.parsed_runs[name] = run_data
            self.run_list.addItem(name)

    def execute_selected_run(self):
        selected = self.run_list.currentItem()
        if selected: self.open_run(selected.text())
        else: QMessageBox.warning(self, "Warning", "Please select a Run from the Shelf first.")

    def execute_all_runs(self):
        for i in range(self.run_list.count()):
            self.open_run(self.run_list.item(i).text())

    def open_run(self, run_name):
        if run_name not in self.parsed_runs: return
        
        self.tab_counter += 1
        tab_id = f"tab_{self.tab_counter}"
        
        console = QTextEdit()
        console.setFont(QFont("Consolas", 10))
        console.setReadOnly(True)
        console.setStyleSheet("background-color: #000000; color: #00ff00;")
        
        tab_index = self.tabs.addTab(console, f"▶ {run_name}")
        self.tabs.setCurrentIndex(tab_index)

        # Pass the DB Manager to the thread
        thread = TestRunnerThread(tab_id, self.parsed_runs[run_name], self.db_manager)
        thread.log_signal.connect(self.append_to_tab)
        thread.finished_signal.connect(self.thread_finished)
        
        self.active_threads[tab_id] = {"thread": thread, "console": console}
        thread.start()

    def append_to_tab(self, tab_id, message):
        if tab_id in self.active_threads:
            console = self.active_threads[tab_id]["console"]
            console.append(message)
            console.verticalScrollBar().setValue(console.verticalScrollBar().maximum())

    def thread_finished(self, tab_id):
        if tab_id in self.active_threads:
            self.active_threads[tab_id]["thread"] = None

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        for tab_id, data in list(self.active_threads.items()):
            if data["console"] == widget:
                if data["thread"] and data["thread"].isRunning():
                    data["thread"].stop()
                    data["thread"].wait()
                del self.active_threads[tab_id]
                break
        self.tabs.removeTab(index)

    def save_shelf(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Shelf", self.workspace_dir, "Shelf Files (*.shelf);;All Files (*)")
        if file_name:
            with open(file_name, 'w') as f: f.write(self.editor.toPlainText())

    def load_shelf(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Shelf", self.workspace_dir, "Shelf Files (*.shelf);;All Files (*)")
        if file_name:
            with open(file_name, 'r') as f: self.editor.setPlainText(f.read())
            self.parse_shelf()

    def closeEvent(self, event):
        for data in self.active_threads.values():
            if data["thread"] and data["thread"].isRunning():
                data["thread"].stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    dialog = WorkspaceDialog()
    workspace_dir = dialog.workspace_path if dialog.exec() == QDialog.DialogCode.Accepted else os.getcwd()
        
    window = ProTestIDE(workspace_dir)
    window.show()
    sys.exit(app.exec())