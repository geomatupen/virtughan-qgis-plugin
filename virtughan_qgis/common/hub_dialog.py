import os
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import (
    QDialog, QListWidget, QListWidgetItem, QStackedWidget,
    QHBoxLayout, QVBoxLayout, QWidget, QDockWidget,
    QFrame, QAbstractItemView, QApplication, QStyle
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication, Qgis, QgsMessageLog

from ..engine.engine_widget import EngineDockWidget
from ..extractor.extractor_widget import ExtractorDockWidget
from ..tiler.tiler_widget import TilerDockWidget  # adjust if needed


PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_icon(rel_path: str, fallback: QStyle.StandardPixmap = QStyle.SP_FileDialogListView) -> QIcon:

    if rel_path.startswith(":/"):
        ic = QIcon(rel_path)
        if not ic.isNull():
            return ic

    abs_path = os.path.normpath(os.path.join(PLUGIN_ROOT, rel_path))
    if os.path.exists(abs_path):
        ic = QIcon(abs_path)
        if not ic.isNull():
            return ic

    # fallback
    QgsMessageLog.logMessage(f"[VirtuGhan] Icon not found, using fallback: {abs_path}", "VirtuGhan", Qgis.Warning)
    return QApplication.style().standardIcon(fallback)


class VirtughanHubDialog(QDialog):
    def __init__(self, iface, start_page: str = "engine", parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("VirtuGhan")
        self.resize(700, 680)

        root = QHBoxLayout(self)

        self.nav = QListWidget()
        self.nav.setObjectName("virtNav")
        self.nav.setSelectionMode(self.nav.SingleSelection)
        self.nav.setAlternatingRowColors(False)
        self.nav.setFixedWidth(240)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.nav.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setSpacing(0) 

        self.pages = QStackedWidget()
        self.pages.setObjectName("virtPages")

        root.addWidget(self.nav)
        root.addWidget(self.pages, 1)

        self._add_page("Engine",    EngineDockWidget(self.iface),    load_icon("../static/images/virtughan-logo.png"))
        self._add_page("Extractor", ExtractorDockWidget(self.iface), load_icon("../static/images/virtughan-logo.png"))
        self._add_page("Tiler",     TilerDockWidget(self.iface),     load_icon("../static/images/virtughan-logo.png"))

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

        # select initial page
        start_index = {"engine": 0, "extractor": 1, "tiler": 2}.get(start_page.lower(), 0)
        self.nav.setCurrentRow(start_index)

        # Styling 
        self.setStyleSheet("""
            QDialog { background: palette(window); }

            /* LEFT NAV */
            QListWidget#virtNav, QListView#virtNav, QListView#virtNav::viewport {
                background: #494d57;             
                color: #e9e9e9;
                border: none;
                outline: none;
            }
            
            QListWidget#virtNav::item {
                padding: 6px 12px;                
                margin: 0;
                border: none;
            }
            QListWidget#virtNav::item:hover {
                background: #2a2f38;
            }
            QListWidget#virtNav::item:selected {
                background: #394150;               
                color: #ffffff;
            }

            /* RIGHT PAGES */
            QStackedWidget#virtPages {
                background: palette(window);
            }
        """)

    def _add_page(self, title: str, dock: QDockWidget, icon: QIcon):
        # Strip dock chrome so it looks like a plain page
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setAllowedAreas(Qt.NoDockWidgetArea)
        dock.setTitleBarWidget(QWidget(dock)) 

        # Wrap the dock in a plain QWidget page
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(dock)
        self.pages.addWidget(page)

        # Sidebar item with enforced height
        item = QListWidgetItem(icon, title)
        item.setSizeHint(QSize(200, 32))  
        self.nav.addItem(item)
