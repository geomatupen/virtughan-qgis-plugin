from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsProcessingAlgorithm
import os

class MyPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.menu = "&My Processing Plugin"

    def initGui(self):
        self.engine_action = QAction("Run Engine", self.iface.mainWindow())
        self.engine_action.triggered.connect(self.run_engine)
        self.iface.addPluginToMenu(self.menu, self.engine_action)

    def unload(self):
        self.iface.removePluginMenu(self.menu, self.engine_action)

    def run_engine(self):
        from .engine.engine_dialog import EngineDialog
        dlg = EngineDialog(self.iface.mainWindow())
        dlg.show()
        dlg.exec_()
