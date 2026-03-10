import sys
import subprocess
import time
import re
import os
import json
import shlex
import signal
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPlainTextEdit, QToolBar, QFileDialog, QTabWidget, QTextEdit,
    QDialog, QPushButton, QLabel, QHBoxLayout, QSplitter,
    QStatusBar, QListWidget, QListWidgetItem, QFormLayout, QLineEdit,
    QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRegularExpression, QRect
from PyQt6.QtGui import (
    QFont, QColor, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QPainter, QTextFormat
)

# ==========================================
# 🎨 DARK THEME (VS CODE STYLE)
# ==========================================
DARK_THEME = """
QMainWindow { background-color: #1e1e1e; }
QWidget { background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', sans-serif; }
QPlainTextEdit, QTextEdit {
    background-color: #1e1e1e; color: #d4d4d4; border: none;
    font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;
}
QListWidget { background-color: #252526; border: 1px solid #333; outline: none; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background-color: #37373d; color: white; }
QTabWidget::pane { border: 1px solid #3e3e42; }
QTabBar::tab { background: #2d2d2d; color: #969696; padding: 8px 15px; border-right: 1px solid #1e1e1e; }
QTabBar::tab:selected { background: #1e1e1e; color: white; border-top: 2px solid #007acc; }
QSplitter::handle { background-color: #3e3e42; }
QToolBar { background: #333333; border-bottom: 1px solid #2b2b2b; spacing: 10px; padding: 5px; }
QPushButton { background-color: #0e639c; color: white; border: none; padding: 6px 12px; border-radius: 2px; }
QPushButton:hover { background-color: #1177bb; }
QStatusBar { background: #007acc; color: white; }
QLineEdit { background-color: #3c3c3c; color: white; border: 1px solid #555; padding: 4px; }
QScrollArea { border: 1px solid #333; background-color: #1e1e1e; }
QScrollBar:vertical { background: #1e1e1e; width: 12px; }
QScrollBar::handle:vertical { background: #424242; min-height: 20px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #4f4f4f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""

# Language configuration: extension -> (build_command, run_command, needs_compilation)
LANG_CONFIG = {
    '.py':  (None, ['{python}', '{file}'], False),
    '.js':  (None, ['{node}', '{file}'], False),
    '.sh':  (None, ['{bash}', '{file}'], False),
    '.go':  (None, ['{go}', 'run', '{file}'], False),
    '.java':(None, ['{java}', '{file}'], False),
    '.cpp': (['{gpp}', '{file}', '-o', '{exe}'], ['{exe}'], True),
    '.rs':  (['{rustc}', '{file}'], ['{exe}'], True),
}

# ==========================================
# 🗂️ HISTORY MANAGER
# ==========================================
class HistoryManager:
    """Manages recent files list stored in ~/.mddt_history.json."""
    def __init__(self):
        self.history_file = Path.home() / ".mddt_history.json"
        self.history = self.load()

    def load(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def add(self, filepath):
        filepath = str(Path(filepath).resolve())
        if filepath in self.history:
            self.history.remove(filepath)
        self.history.insert(0, filepath)
        self.history = self.history[:10]
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f)
        except OSError as e:
            print(f"Warning: Could not write history file: {e}")

# ==========================================
# 📝 EDITOR WITH LINE NUMBERS
# ==========================================
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QRect(0, 0, self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.lineNumberAreaPaintEvent(event)

class CodeEditor(QPlainTextEdit):
    """Text editor with line numbers and syntax highlighting."""
    def __init__(self):
        super().__init__()
        self.highlighter = ShelfHighlighter(self.document())
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2a2d2e")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#6f6f6f"))
                painter.drawText(0, top, self.line_number_area.width() - 3, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

class ShelfHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#c586c0"))
        keyword_fmt.setFontWeight(QFont.Weight.Bold)
        for word in ["run", "file", "cmd", "dir", "env", "compilers"]:
            self.rules.append((QRegularExpression(f"\\b{word}\\b"), keyword_fmt))

        env_var_fmt = QTextCharFormat()
        env_var_fmt.setForeground(QColor("#9cdcfe"))
        self.rules.append((QRegularExpression(r"\benv_[a-zA-Z0-9_]+\b"), env_var_fmt))

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor("#ce9178"))
        self.rules.append((QRegularExpression(r"\".*?(?<!\\)\""), string_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6a9955"))
        self.rules.append((QRegularExpression("#[^\n]*"), comment_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

# ==========================================
# ⚙️ THREADED RUNNER (MULTI-LANGUAGE)
# ==========================================
class TestRunnerThread(QThread):
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(str, str)

    def __init__(self, tab_id, run_data, global_env, compilers, base_dir):
        super().__init__()
        self.tab_id = tab_id
        self.run_data = run_data
        self.global_env = global_env
        self.compilers = compilers
        self.base_dir = base_dir
        self._stop_requested = False
        self.process = None

    def emit_log(self, msg):
        self.log_signal.emit(self.tab_id, msg)

    def run(self):
        name = self.run_data.get('name', 'Unknown')
        self.emit_log(f"🚀 STARTING: {name}")
        try:
            # 1. Resolve Paths
            if 'file' in self.run_data:
                script_rel_path = self.run_data['file']
                full_script_path = os.path.abspath(os.path.join(self.base_dir, script_rel_path))
                cwd = os.path.dirname(full_script_path)
                filename = os.path.basename(full_script_path)
                ext = os.path.splitext(filename)[1].lower()
                
                # Check if file actually exists
                if not os.path.exists(full_script_path):
                    self.emit_log(f"❌ ERROR: Script file not found:\n   {full_script_path}")
                    self.finished_signal.emit(self.tab_id, "Fail")
                    return
            else:
                cwd = os.path.abspath(os.path.join(self.base_dir, self.run_data.get('dir', './')))
                ext = None
                filename = None

            # Check if working directory exists
            if not os.path.exists(cwd):
                self.emit_log(f"❌ ERROR: Working directory not found:\n   {cwd}")
                self.finished_signal.emit(self.tab_id, "Fail")
                return

            # 2. Build Command
            cmd_list, needs_exe = self._build_command(ext, filename, cwd)
            if cmd_list is None:
                self.finished_signal.emit(self.tab_id, "Fail")
                return

            # 3. Setup Environment
            merged_env = os.environ.copy()
            merged_env.update(self.global_env)
            merged_env.update(self.run_data.get('env', {}))

            self.emit_log(f"📂 CWD: {cwd}")
            self.emit_log(f"💻 CMD: {' '.join(shlex.quote(str(x)) for x in cmd_list)}\n{'-'*50}")

            start_time = time.time()
            status = "Pass"

            # 4. Execute Process
            self.process = subprocess.Popen(
                cmd_list,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=merged_env,
                preexec_fn=os.setsid if os.name != 'nt' else None,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )

            # 5. Read Output
            while not self._stop_requested:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None:
                    break
                if line:
                    self.emit_log(line.rstrip())

            if self._stop_requested:
                self.emit_log("\n⛔ Stopped by user")
                self._kill_process_tree()
                status = "Stopped"
            elif self.process.returncode != 0:
                status = "Fail"

            duration = time.time() - start_time
            self.emit_log(f"\n{'-'*50}\n🏁 FINISHED in {duration:.2f}s | Status: {status}")

        except Exception as e:
            self.emit_log(f"\n❌ ERROR: {str(e)}")
            status = "Fail"

        self.finished_signal.emit(self.tab_id, status)

    def _build_command(self, ext, filename, cwd):
        if ext is None:
            cmd_str = self.run_data.get('cmd', '')
            if not cmd_str:
                self.emit_log("❌ No file or cmd specified.")
                return None, False
            return cmd_str, True

        if ext not in LANG_CONFIG:
            self.emit_log(f"❌ Unsupported file extension: {ext}")
            return None, False

        build_cmd, run_cmd, needs_compilation = LANG_CONFIG[ext]

        # Helper to find compilers even if they have version numbers (e.g., "python3.9")
        def get_comp(prefix, default):
            if prefix in self.compilers:
                return self.compilers[prefix]
            for k, v in self.compilers.items():
                if k.startswith(prefix):
                    return v
            return default

        placeholders = {
            "python": get_comp("python", "python"),
            "node": get_comp("node", "node"),
            "bash": get_comp("bash", "bash"),
            "go": get_comp("go", "go"),
            "java": get_comp("java", "java"),
            "gpp": get_comp("g++", get_comp("cpp", "g++")),
            "rustc": get_comp("rust", "rustc"),
            "file": filename,
            "exe": filename[:-4] + (".exe" if os.name == 'nt' else "")
        }

        if needs_compilation:
            build_cmd_expanded = [part.format(**placeholders) for part in build_cmd]
            self.emit_log(f"🔨 Compiling: {' '.join(shlex.quote(p) for p in build_cmd_expanded)}")
            
            try:
                build_proc = subprocess.run(build_cmd_expanded, cwd=cwd, capture_output=True, text=True)
                if build_proc.returncode != 0:
                    self.emit_log("❌ Compilation failed:")
                    self.emit_log(build_proc.stderr)
                    return None, False
            except Exception as e:
                self.emit_log(f"❌ Compilation error: {e}")
                return None, False
                
            run_cmd_expanded = [part.format(**placeholders) for part in run_cmd]
            return run_cmd_expanded, False
        else:
            run_cmd_expanded = [part.format(**placeholders) for part in run_cmd]
            return run_cmd_expanded, False

    def _kill_process_tree(self):
        if self.process is None:
            return
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True)
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except Exception as e:
            self.emit_log(f"⚠️ Error killing process: {e}")

    def stop(self):
        self._stop_requested = True
        if self.process:
            self._kill_process_tree()
# ==========================================
# ⚙️ COMPILER SETTINGS DIALOG (DYNAMIC & AUTO-SCAN)
# ==========================================
class CompilerSettingsDialog(QDialog):
    def __init__(self, current_compilers, current_env, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compiler & Environment Settings")
        self.setMinimumSize(700, 600)
        self.setStyleSheet(DARK_THEME)

        self.compilers = current_compilers.copy()
        self.env = current_env.copy()
        
        # Lists to hold tuples of (key_edit, value_edit, row_layout)
        self.compiler_inputs = []
        self.env_inputs = []

        layout = QVBoxLayout()
        splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Compilers Section ---
        comp_widget = QWidget()
        comp_layout = QVBoxLayout(comp_widget)
        comp_layout.setContentsMargins(0, 0, 0, 0)
        
        comp_header = QHBoxLayout()
        comp_lbl = QLabel("Compiler Paths")
        comp_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        comp_scan_btn = QPushButton("🔍 Auto-Scan")
        comp_scan_btn.clicked.connect(self.auto_scan_compilers)
        
        comp_add_btn = QPushButton("➕ Add Compiler")
        comp_add_btn.clicked.connect(lambda: self.add_compiler_row())
        
        comp_header.addWidget(comp_lbl)
        comp_header.addStretch()
        comp_header.addWidget(comp_scan_btn)
        comp_header.addWidget(comp_add_btn)
        comp_layout.addLayout(comp_header)

        self.comp_scroll = QScrollArea()
        self.comp_scroll.setWidgetResizable(True)
        self.comp_inner = QWidget()
        self.comp_inner_layout = QVBoxLayout(self.comp_inner)
        self.comp_inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.comp_scroll.setWidget(self.comp_inner)
        comp_layout.addWidget(self.comp_scroll)
        
        splitter.addWidget(comp_widget)

        # --- Environment Section ---
        env_widget = QWidget()
        env_layout = QVBoxLayout(env_widget)
        env_layout.setContentsMargins(0, 0, 0, 0)
        
        env_header = QHBoxLayout()
        env_lbl = QLabel("Global Environment Variables")
        env_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        env_add_btn = QPushButton("➕ Add Env Var")
        env_add_btn.clicked.connect(lambda: self.add_env_row())
        
        env_header.addWidget(env_lbl)
        env_header.addStretch()
        env_header.addWidget(env_add_btn)
        env_layout.addLayout(env_header)

        self.env_scroll = QScrollArea()
        self.env_scroll.setWidgetResizable(True)
        self.env_inner = QWidget()
        self.env_inner_layout = QVBoxLayout(self.env_inner)
        self.env_inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.env_scroll.setWidget(self.env_inner)
        env_layout.addWidget(self.env_scroll)

        splitter.addWidget(env_widget)
        layout.addWidget(splitter)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("📥 Import from .mddt")
        import_btn.clicked.connect(self.import_settings)
        save_btn = QPushButton("💾 Save Settings")
        save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(import_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        self._refresh_compiler_inputs()
        self._refresh_env_inputs()

    def add_compiler_row(self, name="", path=""):
        row = QHBoxLayout()
        
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Name (e.g., python3.9)")
        name_edit.setFixedWidth(150)
        
        path_edit = QLineEdit(path)
        path_edit.setPlaceholderText("Executable Path")
        
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(lambda: self.browse_path(path_edit))
        
        remove_btn = QPushButton("✖")
        remove_btn.setFixedWidth(30)
        remove_btn.clicked.connect(lambda: self.remove_compiler_row(row))
        
        row.addWidget(name_edit)
        row.addWidget(path_edit)
        row.addWidget(browse_btn)
        row.addWidget(remove_btn)
        
        self.comp_inner_layout.addLayout(row)
        self.compiler_inputs.append((name_edit, path_edit, row))

    def remove_compiler_row(self, row):
        for i in reversed(range(row.count())):
            widget = row.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.comp_inner_layout.removeItem(row)
        self.compiler_inputs = [item for item in self.compiler_inputs if item[2] != row]

    def browse_path(self, path_edit):
        filter_str = "Executables (*.exe);;All Files (*)" if os.name == 'nt' else "All Files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Select Executable", "", filter_str)
        if path:
            path_edit.setText(path)

    def auto_scan_compilers(self):
        """Scans the system PATH for common compilers and different versions."""
        common_exes = [
            "python", "python3", "python3.8", "python3.9", "python3.10", "python3.11", "python3.12",
            "node", "rustc", "g++", "gcc", "go", "java", "bash", "sh"
        ]
        
        found_count = 0
        existing_names = [item[0].text().strip() for item in self.compiler_inputs]
        
        for exe in common_exes:
            path = shutil.which(exe)
            if path:
                path = os.path.normpath(path).replace('\\', '/')
                if exe not in existing_names:
                    self.add_compiler_row(exe, path)
                    existing_names.append(exe)
                    found_count += 1
                    
        QMessageBox.information(self, "Scan Complete", f"Found and added {found_count} compilers.")

    def _refresh_compiler_inputs(self):
        for item in list(self.compiler_inputs):
            self.remove_compiler_row(item[2])
        self.compiler_inputs = []
        
        for key, value in self.compilers.items():
            self.add_compiler_row(key, value)
            
        if not self.compilers:
            self.add_compiler_row()

    def add_env_row(self, key="", value=""):
        row = QHBoxLayout()
        
        key_edit = QLineEdit(key)
        key_edit.setPlaceholderText("Key")
        key_edit.setFixedWidth(150)
        
        value_edit = QLineEdit(value)
        value_edit.setPlaceholderText("Value")
        
        remove_btn = QPushButton("✖")
        remove_btn.setFixedWidth(30)
        remove_btn.clicked.connect(lambda: self.remove_env_row(row))
        
        row.addWidget(key_edit)
        row.addWidget(value_edit)
        row.addWidget(remove_btn)
        
        self.env_inner_layout.addLayout(row)
        self.env_inputs.append((key_edit, value_edit, row))

    def remove_env_row(self, row):
        for i in reversed(range(row.count())):
            widget = row.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.env_inner_layout.removeItem(row)
        self.env_inputs = [item for item in self.env_inputs if item[2] != row]

    def _refresh_env_inputs(self):
        for item in list(self.env_inputs):
            self.remove_env_row(item[2])
        self.env_inputs = []
        
        for key, value in self.env.items():
            self.add_env_row(key, value)
            
        if not self.env:
            self.add_env_row()

    def import_settings(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Settings", "", "MDDT Files (*.mddt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    # Import compilers dynamically
                    comp_match = re.search(r'^\s*compilers\s*\{([^}]+)\}', text, re.MULTILINE | re.DOTALL)
                    if comp_match:
                        self.compilers = {}
                        for line in comp_match.group(1).split('\n'):
                            if ':' in line and not line.strip().startswith('#'):
                                k, v = line.split(':', 1)
                                self.compilers[k.strip()] = v.strip().strip('"').strip("'")
                        self._refresh_compiler_inputs()
                        
                    # Import env dynamically
                    env_match = re.search(r'^\s*env\s*\{([^}]+)\}', text, re.MULTILINE | re.DOTALL)
                    if env_match:
                        self.env = {}
                        for line in env_match.group(1).split('\n'):
                            if ':' in line and not line.strip().startswith('#'):
                                k, v = line.split(':', 1)
                                self.env[k.strip()] = v.strip().strip('"').strip("'")
                        self._refresh_env_inputs()
            except Exception as e:
                QMessageBox.warning(self, "Import Error", f"Could not import settings:\n{e}")

    def save_settings(self):
        # Collect compilers
        self.compilers = {}
        for name_edit, path_edit, _ in self.compiler_inputs:
            name = name_edit.text().strip()
            path = path_edit.text().strip()
            if name:
                self.compilers[name] = path

        # Collect env
        self.env = {}
        for key_edit, val_edit, _ in self.env_inputs:
            key = key_edit.text().strip()
            val = val_edit.text().strip()
            if key:
                self.env[key] = val
                
        self.accept()

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

        self.parsed_runs = []
        self.global_env = {}
        self.compilers = {}
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
            ("➕ Add File", self.auto_generate_run),
            ("⚙️ Compiler Settings", self.open_compiler_settings),
            ("|", None),
            ("▶ Run Selected", self.execute_selected_run),
            ("⏭ Run All", self.execute_all_runs),
            ("⏹ Stop All", self.stop_all_runs)
        ]

        for label, func in actions:
            if label == "|":
                toolbar.addSeparator()
            else:
                btn = QPushButton(label)
                btn.clicked.connect(func)
                toolbar.addWidget(btn)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

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

        self.editor = CodeEditor()
        self.editor.textChanged.connect(self.parse_script)
        top_splitter.addWidget(self.editor)
        top_splitter.setSizes([250, 800])
        main_splitter.addWidget(top_splitter)

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
            default_code = """# Compiler Paths (Optional)
compilers {
    # python: "C:/Python39/python.exe"
    # node: "C:/Program Files/nodejs/node.exe"
}

# Global Environment Variables
env {
    DB_HOST: "localhost"
    PORT: "8080"
}

run "Bench-1" {
    file: "../python/bench/bench-1.py"
}

run "Bench-2" {
    file: "../JavaScript/bench/bench-1.js"
    env_PORT: "9090" # Overrides global PORT
}

run "Bench-3" {
    file: "../rust/src/bench/bench-1.rs"
}
"""
            self.editor.setPlainText(default_code)
            self.save_file()

        self.parse_script()
        self.status_bar.showMessage("File loaded successfully.", 3000)

    def save_file(self):
        with open(self.current_file, 'w', encoding='utf-8') as f:
            f.write(self.editor.toPlainText())
        self.status_bar.showMessage("File saved.", 3000)

    def auto_generate_run(self):
        base_dir = os.path.dirname(self.current_file)
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Script to Add", base_dir, "All Files (*)")

        if file_path:
            rel_path = os.path.relpath(file_path, base_dir).replace("\\", "/")
            if not rel_path.startswith("."):
                rel_path = "./" + rel_path
            run_name = Path(file_path).stem.replace("_", " ").title()
            block = f'\nrun "{run_name}" {{\n    file: "{rel_path}"\n}}\n'
            self.editor.appendPlainText(block)

    def open_compiler_settings(self):
        dialog = CompilerSettingsDialog(self.compilers, self.global_env, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.compilers = dialog.compilers
            self.global_env = dialog.env
            self.update_editor_blocks()
            self.save_file()

    def update_editor_blocks(self):
        text = self.editor.toPlainText()

        comp_block = "compilers {\n"
        for lang, path in self.compilers.items():
            comp_block += f'    {lang}: "{path}"\n'
        comp_block += "}"

        env_block = "env {\n"
        for key, value in self.global_env.items():
            env_block += f'    {key}: "{value}"\n'
        env_block += "}"

        if re.search(r'^\s*compilers\s*\{[^}]*\}', text, re.MULTILINE):
            text = re.sub(r'^\s*compilers\s*\{[^}]*\}', comp_block, text, flags=re.MULTILINE)
        else:
            text = comp_block + "\n\n" + text

        if re.search(r'^\s*env\s*\{[^}]*\}', text, re.MULTILINE):
            text = re.sub(r'^\s*env\s*\{[^}]*\}', env_block, text, flags=re.MULTILINE)
        else:
            if re.search(r'^\s*compilers\s*\{', text):
                text = re.sub(r'(^\s*compilers\s*\{[^}]*\})', r'\1\n\n' + env_block, text, flags=re.MULTILINE)
            else:
                text = env_block + "\n\n" + text

        self.editor.setPlainText(text)

    def parse_script(self):
        text = self.editor.toPlainText()
        self.parsed_runs = []
        self.global_env = {}
        self.compilers = {}
        self.run_list.clear()

        comp_match = re.search(r'^\s*compilers\s*\{([^}]+)\}', text, re.MULTILINE | re.DOTALL)
        if comp_match:
            for line in comp_match.group(1).split('\n'):
                line = line.strip()
                if ':' in line and not line.startswith('#'):
                    k, v = line.split(':', 1)
                    self.compilers[k.strip()] = v.strip().strip('"').strip("'")

        env_match = re.search(r'^\s*env\s*\{([^}]+)\}', text, re.MULTILINE | re.DOTALL)
        if env_match:
            for line in env_match.group(1).split('\n'):
                line = line.strip()
                if ':' in line and not line.startswith('#'):
                    k, v = line.split(':', 1)
                    self.global_env[k.strip()] = v.strip().strip('"').strip("'")

        block_pattern = re.compile(r'^\s*run\s+"([^"]+)"\s*\{([^}]+)\}', re.MULTILINE | re.DOTALL)
        for match in block_pattern.finditer(text):
            name, body = match.group(1), match.group(2)

            run_data = {"name": name, "env": {}}

            file_m = re.search(r'file:\s*"([^"]+)"', body)
            cmd_m = re.search(r'cmd:\s*"([^"]+)"', body)
            dir_m = re.search(r'dir:\s*"([^"]+)"', body)

            if file_m:
                run_data["file"] = file_m.group(1)
            else:
                run_data["cmd"] = cmd_m.group(1) if cmd_m else ""
                run_data["dir"] = dir_m.group(1) if dir_m else "./"

            for env_m in re.finditer(r'env_([a-zA-Z0-9_]+):\s*"([^"]+)"', body):
                run_data["env"][env_m.group(1)] = env_m.group(2)

            self.parsed_runs.append(run_data)

            display_name = f"🧪 {name}"
            if file_m:
                ext = Path(file_m.group(1)).suffix
                display_name += f" ({ext})"

            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, len(self.parsed_runs) - 1)
            self.run_list.addItem(item)

    def execute_selected_run(self):
        selected = self.run_list.currentItem()
        if selected:
            index = selected.data(Qt.ItemDataRole.UserRole)
            self.open_run(index)
        else:
            self.status_bar.showMessage("⚠️ Select a test first.", 3000)

    def execute_all_runs(self):
        for i in range(self.run_list.count()):
            index = self.run_list.item(i).data(Qt.ItemDataRole.UserRole)
            self.open_run(index)

    def stop_all_runs(self):
        for console, data in list(self.active_threads.items()):
            thread = data.get("thread")
            if thread and thread.isRunning():
                thread.stop()
                thread.wait()
        self.status_bar.showMessage("Stopped all runs.", 3000)

    def open_run(self, run_index):
        if run_index < 0 or run_index >= len(self.parsed_runs):
            return

        run_data = self.parsed_runs[run_index]
        run_name = run_data["name"]

        self.tab_counter += 1
        tab_id = f"tab_{self.tab_counter}"

        console = QPlainTextEdit()
        console.setReadOnly(True)
        console.setStyleSheet("background-color: #1e1e1e; color: #cccccc; font-family: Consolas;")

        tab_title = f"▶ {run_name}"
        if "file" in run_data:
            tab_title += f" ({Path(run_data['file']).suffix})"

        tab_index = self.tabs.addTab(console, tab_title)
        self.tabs.setCurrentIndex(tab_index)

        base_dir = os.path.dirname(self.current_file)

        thread = TestRunnerThread(tab_id, run_data, self.global_env, self.compilers, base_dir)
        thread.log_signal.connect(self.append_to_tab)
        thread.finished_signal.connect(self.thread_finished)

        self.active_threads[console] = {"thread": thread, "index": tab_index, "tab_id": tab_id}
        thread.start()
        self.status_bar.showMessage(f"Running {run_name}...")

    def append_to_tab(self, tab_id, message):
        for console, data in self.active_threads.items():
            if data["tab_id"] == tab_id:
                console.appendPlainText(message)
                cursor = console.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                console.setTextCursor(cursor)
                break

    def thread_finished(self, tab_id, status):
        for console, data in list(self.active_threads.items()):
            if data["tab_id"] == tab_id:
                idx = data["index"]
                icon = "✅" if status == "Pass" else "❌" if status == "Fail" else "⏹"
                old_text = self.tabs.tabText(idx).replace("▶ ", "").replace("✅ ", "").replace("❌ ", "").replace("⏹ ", "")
                self.tabs.setTabText(idx, f"{icon} {old_text}")
                self.status_bar.showMessage(f"Finished ({status})", 3000)
                data["thread"] = None
                break

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        if widget in self.active_threads:
            data = self.active_threads[widget]
            if data["thread"] and data["thread"].isRunning():
                data["thread"].stop()
                data["thread"].wait()
            del self.active_threads[widget]
        self.tabs.removeTab(index)

    def closeEvent(self, event):
        self.save_file()
        for data in self.active_threads.values():
            if data["thread"] and data["thread"].isRunning():
                data["thread"].stop()
                data["thread"].wait()
        event.accept()

# ==========================================
# 🚀 STARTUP DIALOG
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

        btn_layout = QHBoxLayout()
        btn_new = QPushButton("📄 Create New .mddt File")
        btn_new.clicked.connect(self.create_new)
        btn_open = QPushButton("📂 Open Existing .mddt")
        btn_open.clicked.connect(self.open_existing)

        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_open)
        layout.addLayout(btn_layout)

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
            if not file_path.endswith(".mddt"):
                file_path += ".mddt"
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