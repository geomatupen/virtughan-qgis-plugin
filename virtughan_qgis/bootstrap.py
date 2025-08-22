# virtughan_qgis/bootstrap.py
import importlib
import os
import sys
import subprocess
import threading
import queue
from qgis.PyQt.QtWidgets import QProgressDialog, QMessageBox
from qgis.PyQt.QtCore import Qt

PKG_NAME = "virtughan"
REQUIRED_VERSION_SPEC = ""
WHEELHOUSE = os.path.join(os.path.dirname(__file__), "wheelhouse")


def _pkg_present():
    try:
        importlib.import_module("virtughan")
        return True
    except ImportError:
        return False


def _pip_cmd_for_pkg():
    exe = sys.executable
    base = [
        exe, "-m", "pip", "install",
        "--disable-pip-version-check",
        "--no-warn-script-location"
    ]
    if os.path.isdir(WHEELHOUSE) and os.listdir(WHEELHOUSE):
        return base + [
            "--no-index", "--find-links", WHEELHOUSE,
            f"{PKG_NAME}{REQUIRED_VERSION_SPEC}"
        ]
    return base + [f"{PKG_NAME}{REQUIRED_VERSION_SPEC}"]


def _install_pkg_silent():
    cmd = _pip_cmd_for_pkg()
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return True, None
    except Exception as e:
        try:
            subprocess.check_call(cmd + ["--user"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            return True, None
        except Exception as e2:
            return False, f"{e}\n{e2}"


def ensure_virtughan_installed(parent=None, quiet=True):
    if _pkg_present():
        return True

    q = queue.Queue()

    def worker():
        ok, err = _install_pkg_silent()
        q.put((ok, err))

    dlg = None
    if not quiet:
        dlg = QProgressDialog("Installing VirtuGhan Python package...", "", 0, 0, parent)
        dlg.setWindowModality(Qt.NonModal)
        dlg.setCancelButton(None)
        dlg.setWindowTitle("VirtuGhan")
        dlg.show()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    ok, err = q.get()

    if dlg:
        dlg.close()

    if ok and _pkg_present():
        return True

    if not quiet and parent:
        QMessageBox.critical(
            parent,
            "VirtuGhan Installation Failed",
            f"Could not install the '{PKG_NAME}' package.\nError: {err or 'Unknown error'}"
        )

    return False
import importlib
import subprocess
import sys
from qgis.PyQt.QtWidgets import QMessageBox, QTextEdit, QDialog, QVBoxLayout, QPushButton, QProgressDialog
from qgis.PyQt.QtCore import Qt

def _try_install():
    """Try simple installation methods"""
    install_commands = [
        [sys.executable, "-m", "pip", "install", "virtughan"],
        [sys.executable, "-m", "pip", "install", "virtughan", "--break-system-packages"],
        ["python3", "-m", "pip", "install", "virtughan", "--break-system-packages"],
        ["pip", "install", "virtughan", "--break-system-packages"],
        ["pip", "install", "virtughan", "--user"]
    ]
    
    for cmd in install_commands:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            if result.returncode == 0:
                return True
        except Exception:
            continue
    
    return False

def ensure_virtughan(parent=None):
    try:
        importlib.import_module("virtughan")
        return True
    except ImportError:
        pass
    
    from qgis.PyQt.QtWidgets import QMessageBox
    
    reply = QMessageBox.question(
        parent,
        "Install VirtuGhan?",
        "VirtuGhan package not found. Try automatic installation?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes
    )
    
    if reply == QMessageBox.Yes:
        dlg = QProgressDialog("Installing VirtuGhan...", "", 0, 0, parent)
        dlg.setWindowModality(Qt.NonModal)
        dlg.setCancelButton(None)
        dlg.show()
        
        success = _try_install()
        dlg.close()
        
        if success:
            try:
                importlib.import_module("virtughan")
                QMessageBox.information(parent, "Success", "VirtuGhan installed successfully!")
                return True
            except ImportError:
                pass
    
    dialog = QDialog(parent)
    dialog.setWindowTitle("Manual Installation Required")
    dialog.setMinimumSize(600, 350)
    
    layout = QVBoxLayout()
    
    instruction_text = """Automatic installation failed. Please install manually:

METHOD 1 - Terminal/Command Prompt:
python3 -m pip install virtughan --break-system-packages

METHOD 2 - Alternative:
pip install virtughan --break-system-packages

METHOD 3 - Windows OSGeo4W Shell:
python -m pip install virtughan

After installation, restart QGIS and try again.
"""
    
    text_edit = QTextEdit()
    text_edit.setPlainText(instruction_text)
    text_edit.setReadOnly(True)
    layout.addWidget(text_edit)
    
    ok_button = QPushButton("OK")
    ok_button.clicked.connect(dialog.accept)
    layout.addWidget(ok_button)
    
    dialog.setLayout(layout)
    dialog.exec_()
    
    return False
