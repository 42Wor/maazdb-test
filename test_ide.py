import sys
import subprocess
import time
import re
import psutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPlainTextEdit, QToolBar, QDockWidget,
    QLabel, QComboBox, QListWidget, QFileDialog, QTabWidget, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QIcon
import pyqtgraph as pg

# ==========================================
# THREAD 1: SYSTEM & PROCESS MONITOR
# ==========================================
class MonitorThread(QThread):
    """Monitors CPU, RAM, Disk, Network, and GPU"""
    update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_disk = psutil.disk_io_counters()
        self.last_net = psutil.net_io_counters()
        self.last_time = time.time()

    def run(self):
        while self.running:
            current_time = time.time()
            dt = current_time - self.last_time

            # CPU & RAM (System wide for stable graphing)
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent

            # Disk I/O (MB/s)
            disk = psutil.disk_io_counters()
            disk_read_mb = (disk.read_bytes - self.last_disk.read_bytes) / (1024 * 1024) / dt
            disk_write_mb = (disk.write_bytes - self.last_disk.write_bytes) / (1024 * 1024) / dt
            self.last_disk = disk

            # Network I/O (MB/s)
            net = psutil.net_io_counters()
            net_recv_mb = (net.bytes_recv - self.last_net.bytes_recv) / (1024 * 1024) / dt
            net_sent_mb = (net.bytes_sent - self.last_net.bytes_sent) / (1024 * 1024) / dt
            self.last_net = net
            self.last_time = current_time

            # GPU (Simulated placeholder to prevent crashes on non-NVIDIA machines)
            gpu_usage = 0.0 

            stats = {
                "cpu": cpu,
                "ram": ram,
                "disk": disk_read_mb + disk_write_mb,
                "net": net_recv_mb + net_sent_mb,
                "gpu": gpu_usage
            }
            
            self.update_signal.emit(stats)
            time.sleep(0.5)

    def stop(self):
        self.running = False

# ==========================================
# THREAD 2: INDIVIDUAL TEST RUNNER
# ==========================================
class TestRunnerThread(QThread):
    """Runs a single test and streams output to a specific tab"""
    log_signal = pyqtSignal(str, str) # tab_id, message
    finished_signal = pyqtSignal(str) # tab_id

    def __init__(self, tab_id, test_data):
        super().__init__()
        self.tab_id = tab_id
        self.test_data = test_data
        self.running = True
        self.process = None

    def run(self):
        name = self.test_data.get('name', 'Unknown')
        cmd = self.test_data.get('cmd', '')
        cwd = self.test_data.get('dir', './')

        self.log_signal.emit(self.tab_id, f"▶ STARTING: {name}\n▶ CMD: {cmd}\n{'-'*40}")
        
        start_time = time.time()
        try:
            self.process = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, shell=True, encoding="utf-8", errors="replace"
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if not self.running:
                    self.process.terminate()
                    break
                self.log_signal.emit(self.tab_id, line.strip())

            self.process.wait()
            duration = time.time() - start_time
            self.log_signal.emit(self.tab_id, f"\n{'-'*40}\n✔ FINISHED in {duration:.2f}s")

        except Exception as e:
            self.log_signal.emit(self.tab_id, f"\n❌ ERROR: {str(e)}")

        self.finished_signal.emit(self.tab_id)

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()

# ==========================================
# MAIN GUI APPLICATION
# ==========================================
class ProTestIDE(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Multi-Language Test IDE")
        self.resize(1400, 900)

        self.parsed_tests = {}
        self.active_threads = {}
        self.tab_counter = 0

        self.init_ui()
        self.start_monitoring()

    def init_ui(self):
        # --- TOOLBAR ---
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        btn_run_sel = QAction("▶ Run Selected", self)
        btn_run_sel.triggered.connect(self.run_selected_test)
        toolbar.addAction(btn_run_sel)

        btn_run_all = QAction("⏭ Run All", self)
        btn_run_all.triggered.connect(self.run_all_tests)
        toolbar.addAction(btn_run_all)

        toolbar.addSeparator()

        btn_save = QAction("💾 Save (.test)", self)
        btn_save.triggered.connect(self.save_file)
        toolbar.addAction(btn_save)

        btn_load = QAction("📂 Load (.test)", self)
        btn_load.triggered.connect(self.load_file)
        toolbar.addAction(btn_load)

        # --- CENTRAL WIDGET (Code Editor) ---
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 11))
        default_code = """# Professional Test Script"""
        self.editor.setPlainText(default_code)
        self.editor.textChanged.connect(self.parse_script)
        self.setCentralWidget(self.editor)

        # --- DOCK 1: TEST EXPLORER (Left) ---
        self.dock_explorer = QDockWidget("Test Explorer", self)
        self.dock_explorer.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        
        self.test_list = QListWidget()
        self.dock_explorer.setWidget(self.test_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_explorer)

        # --- DOCK 2: GRAPHS (Right) ---
        self.dock_graphs = QDockWidget("System Resources", self)
        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        
        pg.setConfigOption('background', '#1e1e1e')
        pg.setConfigOption('foreground', '#d4d4d4')

        self.graphs = {}
        self.curves = {}
        self.data_buffers = {k: [0.0]*60 for k in ["cpu", "ram", "disk", "net", "gpu"]}

        # Create 5 Graphs
        graph_configs = [
            ("cpu", "CPU Usage (%)", '#00ff00', 100),
            ("ram", "RAM Usage (%)", '#00aaff', 100),
            ("disk", "Disk I/O (MB/s)", '#ffaa00', None),
            ("net", "Network I/O (MB/s)", '#ff00ff', None),
            ("gpu", "GPU Usage (%) [Simulated]", '#ff0000', 100)
        ]

        for key, title, color, y_max in graph_configs:
            plot = pg.PlotWidget(title=title)
            plot.setFixedHeight(120)
            if y_max: plot.setYRange(0, y_max)
            curve = plot.plot(pen=pg.mkPen(color=color, width=2))
            graph_layout.addWidget(plot)
            self.graphs[key] = plot
            self.curves[key] = curve

        self.dock_graphs.setWidget(graph_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_graphs)

        # --- DOCK 3: TERMINAL TABS (Bottom) ---
        self.dock_terminal = QDockWidget("Terminal Output", self)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.dock_terminal.setWidget(self.tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_terminal)

        # Initial Parse
        self.parse_script()

    # --- CUSTOM LANGUAGE PARSER (BLOCK SYNTAX) ---
    def parse_script(self):
        text = self.editor.toPlainText()
        self.parsed_tests = {}
        self.test_list.clear()

        # Regex to find blocks: test "Name" { ... }
        block_pattern = re.compile(r'test\s+"([^"]+)"\s*\{([^}]+)\}')
        
        for match in block_pattern.finditer(text):
            name = match.group(1)
            body = match.group(2)

            # Extract properties inside the block
            lang_m = re.search(r'lang:\s*"([^"]+)"', body)
            dir_m = re.search(r'dir:\s*"([^"]+)"', body)
            cmd_m = re.search(r'cmd:\s*"([^"]+)"', body)

            test_data = {
                "name": name,
                "lang": lang_m.group(1) if lang_m else "Unknown",
                "dir": dir_m.group(1) if dir_m else "./",
                "cmd": cmd_m.group(1) if cmd_m else ""
            }

            self.parsed_tests[name] = test_data
            self.test_list.addItem(name)

    # --- GRAPH UPDATES ---
    def start_monitoring(self):
        self.monitor_thread = MonitorThread()
        self.monitor_thread.update_signal.connect(self.update_graphs)
        self.monitor_thread.start()

    def update_graphs(self, stats):
        for key in stats:
            self.data_buffers[key][:-1] = self.data_buffers[key][1:]
            self.data_buffers[key][-1] = stats[key]
            self.curves[key].setData(self.data_buffers[key])

    # --- TEST EXECUTION ---
    def run_selected_test(self):
        selected = self.test_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select a test from the Explorer first.")
            return
        
        test_name = selected.text()
        self.spawn_test(test_name)

    def run_all_tests(self):
        for i in range(self.test_list.count()):
            test_name = self.test_list.item(i).text()
            self.spawn_test(test_name)

    def spawn_test(self, test_name):
        if test_name not in self.parsed_tests:
            return

        test_data = self.parsed_tests[test_name]
        
        # Create a new Tab for this test
        self.tab_counter += 1
        tab_id = f"tab_{self.tab_counter}"
        
        console = QTextEdit()
        console.setFont(QFont("Consolas", 10))
        console.setReadOnly(True)
        console.setStyleSheet("background-color: #000000; color: #00ff00;")
        
        tab_index = self.tabs.addTab(console, f"⚙ {test_name}")
        self.tabs.setCurrentIndex(tab_index)

        # Start Thread
        thread = TestRunnerThread(tab_id, test_data)
        thread.log_signal.connect(self.append_to_tab)
        thread.finished_signal.connect(self.thread_finished)
        
        self.active_threads[tab_id] = {"thread": thread, "console": console}
        thread.start()

    def append_to_tab(self, tab_id, message):
        if tab_id in self.active_threads:
            console = self.active_threads[tab_id]["console"]
            console.append(message)
            scrollbar = console.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def thread_finished(self, tab_id):
        if tab_id in self.active_threads:
            # Keep the console, but remove the thread reference
            self.active_threads[tab_id]["thread"] = None

    def close_tab(self, index):
        # Find which tab_id this is (by matching the widget)
        widget = self.tabs.widget(index)
        for tab_id, data in list(self.active_threads.items()):
            if data["console"] == widget:
                thread = data["thread"]
                if thread and thread.isRunning():
                    thread.stop()
                    thread.wait()
                del self.active_threads[tab_id]
                break
        self.tabs.removeTab(index)

    # --- FILE I/O ---
    def save_file(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Test Script", "", "Test Script (*.test);;All Files (*)")
        if file_name:
            with open(file_name, 'w') as f:
                f.write(self.editor.toPlainText())

    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Test Script", "", "Test Script (*.test);;All Files (*)")
        if file_name:
            with open(file_name, 'r') as f:
                self.editor.setPlainText(f.read())
            self.parse_script()

    def closeEvent(self, event):
        self.monitor_thread.stop()
        for data in self.active_threads.values():
            if data["thread"] and data["thread"].isRunning():
                data["thread"].stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = ProTestIDE()
    window.show()
    sys.exit(app.exec())