from qgis.core import QgsProcessingProvider
from .engine.engine_logic import VirtuGhanEngineAlgorithm
# Later you can add Tiler/Extractor algs here and register them.

class VirtuGhanProcessingProvider(QgsProcessingProvider):
    def id(self): return "virtughan"
    def name(self): return "VirtuGhan"
    def longName(self): return "VirtuGhan"

    def loadAlgorithms(self):
        self.addAlgorithm(VirtuGhanEngineAlgorithm())
