# virtughan_qgis/main_plugin.py
import os
import sys

from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication
from .engine.engine_widget import EngineDockWidget
from .extractor.extractor_widget import ExtractorDockWidget
from qgis.core import QgsApplication
from .processing_provider import VirtuGhanProcessingProvider

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
        self.engine_dock = None
        self.extractor_dock = None
        self.tiler_dock = None
        self.provider = None
        self.action_engine = None
        self.action_extractor = None
        self.action_tiler = None
        self._imports_ready = False
        self._last_import_error = None

    def _ensure_deps_and_imports(self):
        if self._imports_ready:
            return True
        ok = ensure_virtughan_installed(self.iface.mainWindow(), quiet=True)
        if not ok:
            self._last_import_error = "Automatic installation of 'virtughan' failed."
            return False
        try:
            from .engine.engine_widget import EngineDockWidget
            from .extractor.extractor_widget import ExtractorDockWidget
            from .tiler.tiler_widget import TilerDockWidget
            from .processing_provider import VirtuGhanProcessingProvider
            self._EngineDockWidget = EngineDockWidget
            self._ExtractorDockWidget = ExtractorDockWidget
            self._TilerDockWidget = TilerDockWidget
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
                f"VirtuGhan plugin could not initialize:\n\n{self._last_import_error}"
            )
            # Add disabled actions to menu
            self.action_engine = QAction("VirtuGhan • Engine (unavailable)", self.iface.mainWindow())
            self.action_engine.setEnabled(False)
            self.action_extractor = QAction("VirtuGhan • Extractor (unavailable)", self.iface.mainWindow())
            self.action_extractor.setEnabled(False)
            self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
            self.iface.addPluginToMenu("VirtuGhan", self.action_extractor)
            return

        # Engine QAction
        self.action_engine = QAction("VirtuGhan • Engine", self.iface.mainWindow())
        self.action_engine.triggered.connect(self.show_engine)
        self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
        self.iface.addToolBarIcon(self.action_engine)

        # Extractor QAction
        self.action_extractor = QAction("VirtuGhan • Extractor", self.iface.mainWindow())
        self.action_extractor.triggered.connect(self.show_extractor)
        self.iface.addPluginToMenu("VirtuGhan", self.action_extractor)
        self.iface.addToolBarIcon(self.action_extractor)

        # Tiler QAction
        self.action_tiler = QAction("VirtuGhan • Tiler", self.iface.mainWindow())
        self.action_tiler.triggered.connect(self.show_tiler)
        self.iface.addPluginToMenu("VirtuGhan", self.action_tiler)
        self.iface.addToolBarIcon(self.action_tiler)


        # Register processing provider
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
        # Remove Engine action and dock
        if self.action_engine:
            self.iface.removePluginMenu("VirtuGhan", self.action_engine)
            self.iface.removeToolBarIcon(self.action_engine)
            self.action_engine = None
        if self.engine_dock:
            self.iface.removeDockWidget(self.engine_dock)
            self.engine_dock = None

        # Remove Extractor action and dock
        if self.action_extractor:
            self.iface.removePluginMenu("VirtuGhan", self.action_extractor)
            self.iface.removeToolBarIcon(self.action_extractor)
            self.action_extractor = None
        if self.extractor_dock:
            self.iface.removeDockWidget(self.extractor_dock)
            self.extractor_dock = None

        # Remove Tiler action and dock
        if self.action_tiler:
            self.iface.removePluginMenu("VirtuGhan", self.action_tiler)
            self.iface.removeToolBarIcon(self.action_tiler)
            self.action_tiler = None
        if self.tiler_dock:
            self.iface.removeDockWidget(self.tiler_dock)
            self.tiler_dock = None


        # Remove provider
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

    def show_extractor(self):
        if not self._imports_ready and not self._ensure_deps_and_imports():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "VirtuGhan",
                f"Extractor UI cannot be shown because dependencies are missing:\n\n{self._last_import_error}"
            )
            return

        if not self.extractor_dock:
            self.extractor_dock = self._ExtractorDockWidget(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.extractor_dock)
        self.extractor_dock.show()
        self.extractor_dock.raise_()

    def show_tiler(self):
        if not self._imports_ready and not self._ensure_deps_and_imports():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "VirtuGhan",
                f"Tiler UI cannot be shown because dependencies are missing:\n\n{self._last_import_error}"
            )
            return
        if not self.tiler_dock:
            self.tiler_dock = self._TilerDockWidget(self.iface)
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.tiler_dock)
        self.tiler_dock.show()
        self.tiler_dock.raise_()

