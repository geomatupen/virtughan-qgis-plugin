# virtughan_qgis/main_plugin.py
import os
import sys

from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication
from .common.hub_dialog import VirtughanHubDialog

from .common.map_setup import setup_default_map


PLUGIN_DIR = os.path.dirname(__file__)
LIBS_DIR = os.path.join(PLUGIN_DIR, "libs")
if os.path.isdir(LIBS_DIR) and LIBS_DIR not in sys.path:
    sys.path.insert(0, LIBS_DIR)

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
            self.action_engine = QAction("VirtuGhan • Engine (unavailable)", self.iface.mainWindow())
            self.action_engine.setEnabled(False)
            self.action_extractor = QAction("VirtuGhan • Extractor (unavailable)", self.iface.mainWindow())
            self.action_extractor.setEnabled(False)
            self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
            self.iface.addPluginToMenu("VirtuGhan", self.action_extractor)
            return

        self.action_engine = QAction("VirtuGhan • Engine", self.iface.mainWindow())
        self.action_engine.triggered.connect(self.show_engine)
        self.iface.addPluginToMenu("VirtuGhan", self.action_engine)
        self.iface.addToolBarIcon(self.action_engine)

        self.action_extractor = QAction("VirtuGhan • Extractor", self.iface.mainWindow())
        self.action_extractor.triggered.connect(self.show_extractor)
        self.iface.addPluginToMenu("VirtuGhan", self.action_extractor)
        self.iface.addToolBarIcon(self.action_extractor)

        self.action_tiler = QAction("VirtuGhan • Tiler", self.iface.mainWindow())
        self.action_tiler.triggered.connect(self.show_tiler)
        self.iface.addPluginToMenu("VirtuGhan", self.action_tiler)
        self.iface.addToolBarIcon(self.action_tiler)

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
        try:
            if self._hub_dialog:
                self._hub_dialog.close()
        except Exception:
            pass
        self._hub_dialog = None

        if self.action_engine:
            self.iface.removePluginMenu("VirtuGhan", self.action_engine)
            self.iface.removeToolBarIcon(self.action_engine)
            self.action_engine = None
        if self.engine_dock:
            self.iface.removeDockWidget(self.engine_dock)
            self.engine_dock = None

        if self.action_extractor:
            self.iface.removePluginMenu("VirtuGhan", self.action_extractor)
            self.iface.removeToolBarIcon(self.action_extractor)
            self.action_extractor = None
        if self.extractor_dock:
            self.iface.removeDockWidget(self.extractor_dock)
            self.extractor_dock = None

        if self.action_tiler:
            self.iface.removePluginMenu("VirtuGhan", self.action_tiler)
            self.iface.removeToolBarIcon(self.action_tiler)
            self.action_tiler = None
        if self.tiler_dock:
            self.iface.removeDockWidget(self.tiler_dock)
            self.tiler_dock = None

        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except Exception:
                pass
            self.provider = None 

    def _show_hub(self, start_page: str):
        # Optional: add basemap once per click, but skip if already present
        try:
            if getattr(self.iface, "mapCanvas", None) and self.iface.mapCanvas():
                setup_default_map(
                    self.iface,
                    center_wgs84=(85.3240, 27.7172), 
                    scale_m=5000,
                    set_project_crs=False,            # respect current project CRS
                    skip_if_present=True,             # don't add another OSM if present
                    skip_zoom_if_present=True,        # don't re-zoom if OSM is already there
                    zoom_delay_ms=1000,
                )
        except Exception as e:
            # skip if osm map already exists and any issues with map loading
            try:
                self.iface.messageBar().pushWarning("VirtuGhan", f"Basemap skipped: {e}")
            except Exception:
                pass

        # Close previous instance if you want only one hub at a time
        try:
            if self._hub_dialog:
                self._hub_dialog.close()
        except Exception:
            pass

        self._hub_dialog = VirtughanHubDialog(self.iface, start_page=start_page, parent=self.iface.mainWindow())
        self._hub_dialog.setModal(False)
        self._hub_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self._hub_dialog.show()
        self._hub_dialog.raise_()


    def show_engine(self):
        self._show_hub("engine")

    def show_extractor(self):
        self._show_hub("extractor")

    def show_tiler(self):
        self._show_hub("tiler")



