from qgis.core import QgsProcessingProvider
from .engine.engine_logic import VirtuGhanEngineAlgorithm
from .extractor.extractor_logic import VirtuGhanExtractorAlgorithm  # NEW
from qgis.core import QgsProcessingProvider, QgsApplication, QgsProcessingAlgorithm
from qgis.core import QgsProcessingProvider
from .engine.engine_logic import VirtuGhanEngineAlgorithm
from .extractor.extractor_logic import VirtuGhanExtractorAlgorithm

class VirtuGhanProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "virtughan"

    def name(self):
        return "VirtuGhan"

    def loadAlgorithms(self):
        self.addAlgorithm(VirtuGhanEngineAlgorithm())
        self.addAlgorithm(VirtuGhanExtractorAlgorithm())

# class VirtuGhanProvider(QgsProcessingProvider):
#     def id(self): return "virtughan"
#     def name(self): return "VirtuGhan"

#     def loadAlgorithms(self):
#         self.addAlgorithm(VirtuGhanEngineAlgorithm())
#         self.addAlgorithm(VirtuGhanExtractorAlgorithm())  # NEW

