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
REQUIRED_VERSION_SPEC = ""  # e.g., "==0.3.1" if you want to lock version
WHEELHOUSE = os.path.join(os.path.dirname(__file__), "wheelhouse")  # Optional local wheels folder

# ------------------------------
# Internal check if package exists
# ------------------------------
def _pkg_present():
    try:
        importlib.import_module("vcube")  # virtughan's core module name
        return True
    except ImportError:
        return False

# ------------------------------
# Build pip install command
# ------------------------------
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

# ------------------------------
# Install package silently
# ------------------------------
def _install_pkg_silent():
    cmd = _pip_cmd_for_pkg()
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return True, None
    except Exception as e:
        # Fallback with --user if first attempt fails
        try:
            subprocess.check_call(cmd + ["--user"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            return True, None
        except Exception as e2:
            return False, f"{e}\n{e2}"

# ------------------------------
# Public function to ensure virtughan is installed
# ------------------------------
def ensure_virtughan_installed(parent=None, quiet=True):
    """
    Ensures virtughan package is installed.
    Shows a progress dialog if quiet=False.
    Returns True if installed/available, False otherwise.
    """
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

    ok, err = q.get()  # Wait for result

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
