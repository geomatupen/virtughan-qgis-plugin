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
