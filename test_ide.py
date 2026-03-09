import sys
import subprocess
import time
import re
import os
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPlainTextEdit, QToolBar, QFileDialog, QTabWidget, QTextEdit,
    QDialog, QPushButton, QLabel, QHBoxLayout, QSplitter, 
    QStatusBar, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF, QSize, QRegularExpression
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QSyntaxHighlighter, 
    QTextCharFormat, QTextCursor
)

# ==========================================
# 🎨 DARK THEME (VS CODE STYLE)
# ==========================================
DARK_THEME = """
QMainWindow { background-color: #1e1e1e; }
QWidget { background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; }
QPlainTextEdit, QTextEdit { 
    background-color: #1e1e1e; 
    color: #d4d4d4; 
    border: none; 
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
QListWidget { background-color: #252526; border: 1px solid #333; outline: none; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background-color: #37373d; color: white; }
QTabWidget::pane { border: 1px solid #3e3e42; }
QTabBar::tab { 
    background: #2d2d2d; color: #969696; padding: 8px 15px; border-right: 1px solid #1e1e1e;
}
QTabBar::tab:selected { background: #1e1e1e; color: white; border-top: 2px solid #007acc; }
QSplitter::handle { background-color: #3e3e42; }
QToolBar { background: #333333; border-bottom: 1px solid #2b2b2b; spacing: 10px; padding: 5px; }
QPushButton { background-color: #0e639c; color: white; border: none; padding: 6px 12px; border-radius: 2px; }
QPushButton:hover { background-color: #1177bb; }
QStatusBar { background: #007acc; color: white; }
"""

# ==========================================
# 🗂️ HISTORY MANAGER
# ==========================================
class HistoryManager:
    def __init__(self):
        self.history_file = Path.home() / ".mddt_history.json"
        self.history = self.load()

    def load(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def add(self, filepath):
        filepath = str(Path(filepath).resolve())
        if filepath in self.history:
            self.history.remove(filepath)
        self.history.insert(0, filepath)
        self.history = self.history[:10] # Keep last 10
        
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f)

# ==========================================
# 📝 EDITOR & HIGHLIGHTING
# ==========================================
class ShelfHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#c586c0"))
        keyword_fmt.setFontWeight(QFont.Weight.Bold)
        for word in ["run", "file", "cmd", "dir"]:
            self.rules.append((QRegularExpression(f"\\b{word}\\b"), keyword_fmt))

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor("#ce9178"))
        self.rules.append((QRegularExpression("\".*\""), string_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6a9955"))
        self.rules.append((QRegularExpression("#[^\n]*"), comment_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.highlighter = ShelfHighlighter(self.document())
        self.setPlaceholderText("Write your test definitions here...")

# ==========================================
# ⚙️ THREADED RUNNER
# ==========================================
class TestRunnerThread(QThread):
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(str, str)

    def __init__(self, tab_id, run_data, base_dir):
        super().__init__()
        self.tab_id = tab_id
        self.run_data = run_data
        self.base_dir = base_dir # The directory of the .mddt file
        self.running = True
        self.process = None

    def emit_log(self, msg):
        self.log_signal.emit(self.tab_id, msg)

    def run(self):
        name = self.run_data.get('name', 'Unknown')
        
        if 'file' in self.run_data:
            # Resolve the relative path based on the .mddt file's location
            script_rel_path = self.run_data['file']
            full_script_path = os.path.normpath(os.path.join(self.base_dir, script_rel_path))
            
            cwd = os.path.dirname(full_script_path)
            filename = os.path.basename(full_script_path)
            ext = os.path.splitext(filename)[1].lower()
            
            if ext == '.py': cmd = f'python -u "{filename}"'
            elif ext == '.js': cmd = f'node "{filename}"'
            elif ext == '.sh': cmd = f'bash "{filename}"'
            else: cmd = f'"{filename}"'
        else:
            cmd = self.run_data.get('cmd', '')
            cwd = os.path.normpath(os.path.join(self.base_dir, self.run_data.get('dir', './')))

        self.emit_log(f"🚀 STARTING: {name}")
        self.emit_log(f"📂 CWD: {cwd}")
        self.emit_log(f"💻 CMD: {cmd}\n{'-'*50}")
        
        start_time = time.time()
        status = "Pass"
        
        try:
            self.process = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=True, encoding="utf-8", errors="replace", bufsize=1
            )
            while self.running:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None: break
                if line: self.emit_log(line.rstrip())

            if self.process.returncode != 0: status = "Fail"
            duration = time.time() - start_time
            self.emit_log(f"\n{'-'*50}\n🏁 FINISHED in {duration:.2f}s | Status: {status}")

        except Exception as e:
            self.emit_log(f"\n❌ ERROR: {str(e)}")
            status = "Fail"

        self.finished_signal.emit(self.tab_id, status)

    def stop(self):
        self.running = False
        if self.process: self.process.terminate()

# ==========================================
# 🖥️ MAIN IDE
# ==========================================
class MDDTRunnerIDE(QMainWindow):
    def __init__(self, filepath):
        super().__init__()
        self.current_file = filepath
        self.history_manager = HistoryManager()
        
        self.setWindowTitle(f"MDDT Runner - {self.current_file}")
        self.resize(1200, 800)
        self.setStyleSheet(DARK_THEME)

        self.parsed_runs = {}
        self.active_threads = {}
        self.tab_counter = 0

        self.init_ui()
        self.load_file(self.current_file)

    def init_ui(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        actions = [
            ("💾 Save", self.save_file),
            ("|", None),
            ("➕ Add File (Relative)", self.auto_generate_run),
            ("▶ Run Selected", self.execute_selected_run),
            ("⏭ Run All", self.execute_all_runs)
        ]

        for label, func in actions:
            if label == "|": toolbar.addSeparator()
            else:
                btn = QPushButton(label)
                btn.clicked.connect(func)
                toolbar.addWidget(btn)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar
        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0,0,0,0)
        lbl_sidebar = QLabel("  TEST EXPLORER")
        lbl_sidebar.setStyleSheet("background: #252526; color: #bbb; font-weight: bold; padding: 5px;")
        sidebar_layout.addWidget(lbl_sidebar)
        
        self.run_list = QListWidget()
        self.run_list.itemDoubleClicked.connect(self.execute_selected_run)
        sidebar_layout.addWidget(self.run_list)
        top_splitter.addWidget(sidebar_widget)

        # Editor
        self.editor = CodeEditor()
        self.editor.textChanged.connect(self.parse_script)
        top_splitter.addWidget(self.editor)
        top_splitter.setSizes([250, 800])
        main_splitter.addWidget(top_splitter)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setDocumentMode(True)
        main_splitter.addWidget(self.tabs)
        main_splitter.setSizes([600, 200])

        self.setCentralWidget(main_splitter)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def load_file(self, filepath):
        self.current_file = filepath
        self.setWindowTitle(f"MDDT Runner - {self.current_file}")
        self.history_manager.add(filepath)
        
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
        else:
            # Default template for new files
            self.editor.setPlainText("# MDDT Test Script\n\nrun \"Example Test\" {\n    file: \"./src/main.py\"\n}\n")
            self.save_file()
            
        self.parse_script()
        self.status_bar.showMessage("File loaded successfully.", 3000)

    def save_file(self):
        with open(self.current_file, 'w', encoding='utf-8') as f:
            f.write(self.editor.toPlainText())
        self.status_bar.showMessage("File saved.", 3000)

    def auto_generate_run(self):
        # Open file dialog to select a script
        base_dir = os.path.dirname(self.current_file)
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Script to Add", base_dir, "All Files (*)")
        
        if file_path:
            # Calculate RELATIVE path for Git compatibility
            rel_path = os.path.relpath(file_path, base_dir)
            rel_path = rel_path.replace("\\", "/") # Force forward slashes for cross-platform
            
            if not rel_path.startswith("."):
                rel_path = "./" + rel_path

            run_name = Path(file_path).stem.replace("_", " ").title()
            block = f'\nrun "{run_name}" {{\n    file: "{rel_path}"\n}}\n'
            self.editor.appendPlainText(block)

    def parse_script(self):
        text = self.editor.toPlainText()
        self.parsed_runs = {}
        self.run_list.clear()
        block_pattern = re.compile(r'run\s+"([^"]+)"\s*\{([^}]+)\}', re.DOTALL)
        
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
            self.run_list.addItem(QListWidgetItem(f"🧪 {name}"))

    def execute_selected_run(self):
        selected = self.run_list.currentItem()
        if selected: self.open_run(selected.text()[2:])
        else: self.status_bar.showMessage("⚠️ Select a test first.", 3000)

    def execute_all_runs(self):
        for i in range(self.run_list.count()):
            self.open_run(self.run_list.item(i).text()[2:])

    def open_run(self, run_name):
        if run_name not in self.parsed_runs: return
        self.tab_counter += 1
        tab_id = f"tab_{self.tab_counter}"
        
        console = QTextEdit()
        console.setReadOnly(True)
        console.setStyleSheet("background-color: #1e1e1e; color: #cccccc; font-family: Consolas;")
        
        tab_index = self.tabs.addTab(console, f"▶ {run_name}")
        self.tabs.setCurrentIndex(tab_index)

        base_dir = os.path.dirname(self.current_file)
        thread = TestRunnerThread(tab_id, self.parsed_runs[run_name], base_dir)
        thread.log_signal.connect(self.append_to_tab)
        thread.finished_signal.connect(self.thread_finished)
        
        self.active_threads[tab_id] = {"thread": thread, "console": console, "index": tab_index}
        thread.start()
        self.status_bar.showMessage(f"Running {run_name}...")

    def append_to_tab(self, tab_id, message):
        if tab_id in self.active_threads:
            console = self.active_threads[tab_id]["console"]
            console.append(message)
            cursor = console.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            console.setTextCursor(cursor)

    def thread_finished(self, tab_id, status):
        if tab_id in self.active_threads:
            idx = self.active_threads[tab_id]["index"]
            icon = "✅" if status == "Pass" else "❌"
            old_text = self.tabs.tabText(idx).replace("▶ ", "")
            self.tabs.setTabText(idx, f"{icon} {old_text}")
            self.status_bar.showMessage(f"Finished: {old_text} ({status})", 3000)
            self.active_threads[tab_id]["thread"] = None

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        target_id = None
        for tab_id, data in self.active_threads.items():
            if data["console"] == widget:
                target_id = tab_id
                if data["thread"] and data["thread"].isRunning():
                    data["thread"].stop()
                    data["thread"].wait()
                break
        if target_id: del self.active_threads[target_id]
        self.tabs.removeTab(index)

    def closeEvent(self, event):
        self.save_file()
        for data in self.active_threads.values():
            if data["thread"] and data["thread"].isRunning():
                data["thread"].stop()
                data["thread"].wait()
        event.accept()

# ==========================================
# 🚀 STARTUP DIALOG (FILE & HISTORY)
# ==========================================
class StartupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Welcome to MDDT Runner")
        self.setFixedSize(500, 350)
        self.setStyleSheet(DARK_THEME)
        self.selected_file = None
        self.history_manager = HistoryManager()

        layout = QVBoxLayout()
        
        lbl = QLabel("MDDT Test Runner")
        lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        layout.addWidget(lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("📄 Create New .mddt File")
        btn_new.clicked.connect(self.create_new)
        btn_open = QPushButton("📂 Open Existing .mddt")
        btn_open.clicked.connect(self.open_existing)
        
        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_open)
        layout.addLayout(btn_layout)

        # History List
        layout.addWidget(QLabel("\nRecent Files:"))
        self.history_list = QListWidget()
        for path in self.history_manager.history:
            if os.path.exists(path):
                self.history_list.addItem(path)
                
        self.history_list.itemDoubleClicked.connect(self.open_history_item)
        layout.addWidget(self.history_list)

        self.setLayout(layout)

    def create_new(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Create New MDDT File", "", "MDDT Files (*.mddt)")
        if file_path:
            if not file_path.endswith(".mddt"): file_path += ".mddt"
            self.selected_file = file_path
            self.accept()

    def open_existing(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open MDDT File", "", "MDDT Files (*.mddt);;All Files (*)")
        if file_path:
            self.selected_file = file_path
            self.accept()

    def open_history_item(self, item):
        self.selected_file = item.text()
        self.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    dialog = StartupDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_file:
        window = MDDTRunnerIDE(dialog.selected_file)
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit()