# virtughan_qgis/main_plugin.py
import os
import sys

from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication

# Path setup for vendored libs (optional if you include libs/ folder)
PLUGIN_DIR = os.path.dirname(__file__)
LIBS_DIR = os.path.join(PLUGIN_DIR, "libs")
if os.path.isdir(LIBS_DIR) and LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

# Bootstrap for installing virtughan automatically if missing
try:
    from .bootstrap import ensure_virtughan_installed
except Exception:
    def ensure_virtughan_installed(*args, **kwargs):
        return True


class VirtuGhanPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action_engine = None
        self.engine_dock = None
        self.provider = None
        self._imports_ready = False
        self._last_import_error = None

    def _ensure_deps_and_imports(self):
        """Ensure virtughan is installed and import plugin components."""
        if self._imports_ready:
            return True

        # Install virtughan if not present
        ok = ensure_virtughan_installed(self.iface.mainWindow(), quiet=True)
        if not ok:
            self._last_import_error = "Automatic installation of 'virtughan' failed."
            return False

        # Import actual plugin components
        try:
            from .engine.engine_widget import EngineDockWidget
            from .processing_provider import VirtuGhanProcessingProvider
            self._EngineDockWidget = EngineDockWidget
            self._VirtuGhanProcessingProvider = VirtuGhanProcessingProvider
            self._imports_ready = True
            return True
        except Exception as e:
            self._last_import_error = str(e)
            return False

    def initGui(self):
        if not self._ensure_deps_and_imports():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "VirtuGhan",
                f"VirtuGhan plugin could not initialize:\n\n{self._last_import_error}\n"
                "Please check your internet connection or contact support."
            )
            self.action_engine = QAction("VirtuGhan • Engine (unavailable)", self.iface.mainWindow())
            self.action_engine.setEnabled(False)
            self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
            self.iface.addToolBarIcon(self.action_engine)
            return

        # Action for Engine
        self.action_engine = QAction("VirtuGhan • Engine", self.iface.mainWindow())
        self.action_engine.triggered.connect(self.show_engine)
        self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
        self.iface.addToolBarIcon(self.action_engine)

        # Register processing provider (Engine now, Tiler/Extractor later)
        try:
            self.provider = self._VirtuGhanProcessingProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
        except Exception as e:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "VirtuGhan",
                f"Processing provider could not be registered:\n{e}"
            )

    def unload(self):
        if self.action_engine:
            self.iface.removePluginMenu("VirtuGhan", self.action_engine)
            self.iface.removeToolBarIcon(self.action_engine)
            self.action_engine = None
        if self.engine_dock:
            self.iface.removeDockWidget(self.engine_dock)
            self.engine_dock = None
        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except Exception:
                pass
            self.provider = None

    def show_engine(self):
        if not self._imports_ready and not self._ensure_deps_and_imports():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "VirtuGhan",
                f"Engine UI cannot be shown because dependencies are missing:\n\n{self._last_import_error}"
            )
            return

        if not self.engine_dock:
            self.engine_dock = self._EngineDockWidget(self.iface)
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.engine_dock)
        self.engine_dock.show()
        self.engine_dock.raise_()
