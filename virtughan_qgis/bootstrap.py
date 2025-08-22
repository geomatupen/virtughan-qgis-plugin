# virtughan_qgis/bootstrap.py
import importlib
import os
import platform
import subprocess
import sys

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

PKG_NAME = "virtughan"


def _log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(f"VirtuGhan Bootstrap: {msg}", "VirtuGhan", level)


def check_dependencies():
    try:
        import virtughan

        _log("VirtuGhan package found")
        return True
    except ImportError:
        _log("VirtuGhan package not found", Qgis.Warning)
        return False


def _get_safe_python_executable():
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        _log("Running in virtual environment")
        return sys.executable

    candidates = [sys.executable, "python", "python3"]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return "python"


def _try_install_virtughan():
    is_windows = platform.system() == "Windows"
    python_exe = _get_safe_python_executable()

    _log(f"Platform: {platform.system()}")
    _log(f"Python executable: {python_exe}")

    if is_windows:
        install_commands = [
            [python_exe, "-m", "pip", "install", "virtughan", "--user"],
            ["pip", "install", "virtughan", "--user"],
            [python_exe, "-m", "pip", "install", "virtughan"],
        ]
    else:
        install_commands = [
            [
                python_exe,
                "-m",
                "pip",
                "install",
                "virtughan",
                "--break-system-packages",
            ],
            [python_exe, "-m", "pip", "install", "virtughan", "--user"],
            ["pip3", "install", "virtughan", "--break-system-packages"],
            ["pip", "install", "virtughan", "--user"],
        ]

    for i, cmd in enumerate(install_commands):
        try:
            _log(f"Trying installation method {i + 1}: {' '.join(cmd[:4])}")

            kwargs = {
                "capture_output": True,
                "text": True,
                "timeout": 120,
                "cwd": os.path.expanduser("~"),
            }

            if is_windows:
                kwargs["shell"] = True
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(cmd, **kwargs)

            if result.returncode == 0:
                _log(f"Installation successful with method {i + 1}")
                return True, None
            else:
                _log(f"Method {i + 1} failed with return code {result.returncode}")

        except subprocess.TimeoutExpired:
            _log(f"Method {i + 1} timed out")
            continue
        except FileNotFoundError:
            _log(f"Method {i + 1} failed: command not found")
            continue
        except Exception as e:
            _log(f"Method {i + 1} failed with exception: {str(e)}")
            continue

    return False, "All installation methods failed"


def install_dependencies(parent=None, quiet=False):
    if check_dependencies():
        return True

    _log("Starting dependency installation")

    if not quiet and parent:
        reply = QMessageBox.question(
            parent,
            "Install VirtuGhan?",
            "VirtuGhan package not found. Try automatic installation?\n\n"
            "This will attempt to install the package using pip.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply != QMessageBox.Yes:
            _log("User declined installation")
            return False

    try:
        success, error = _try_install_virtughan()

        if success and check_dependencies():
            if not quiet and parent:
                QMessageBox.information(
                    parent,
                    "Success",
                    "VirtuGhan installed successfully!\n\nPlease restart QGIS to ensure proper functionality.",
                )
            _log("Installation completed successfully")
            return True
        else:
            _log(f"Installation failed: {error}", Qgis.Warning)

    except Exception as e:
        _log(f"Installation error: {str(e)}", Qgis.Critical)
        if not quiet and parent:
            QMessageBox.warning(
                parent,
                "Installation Error",
                f"An error occurred during installation:\n{str(e)}",
            )

    if not quiet and parent:
        _show_manual_install_dialog(parent)

    return False


def _show_manual_install_dialog(parent):
    try:
        dialog = QDialog(parent)
        dialog.setWindowTitle("Manual Installation Required")
        dialog.setMinimumSize(650, 400)

        layout = QVBoxLayout()

        is_windows = platform.system() == "Windows"

        if is_windows:
            instruction_text = """Automatic installation failed. Please install manually:

WINDOWS - Method 1 (OSGeo4W Shell):
1. Open OSGeo4W Shell as Administrator
2. Run: python -m pip install virtughan

WINDOWS - Method 2 (Command Prompt):
1. Open Command Prompt as Administrator
2. Run: python -m pip install virtughan --user

WINDOWS - Method 3 (QGIS Python Console):
1. In QGIS, go to Plugins > Python Console
2. Run: import subprocess; subprocess.run(['python', '-m', 'pip', 'install', 'virtughan', '--user'])

After installation, restart QGIS completely.
"""
        else:
            instruction_text = """Automatic installation failed. Please install manually:

LINUX/MAC - Method 1:
python3 -m pip install virtughan --break-system-packages

LINUX/MAC - Method 2:
python3 -m pip install virtughan --user

LINUX/MAC - Method 3 (if using conda):
conda install -c conda-forge pip
pip install virtughan

After installation, restart QGIS.
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

    except Exception as e:
        _log(f"Error showing manual install dialog: {str(e)}", Qgis.Warning)


def ensure_virtughan_installed(parent=None, quiet=True):
    try:
        return install_dependencies(parent, quiet)
    except Exception as e:
        _log(f"Bootstrap error: {str(e)}", Qgis.Critical)
        return check_dependencies()
