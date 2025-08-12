# virtughan_qgis/engine/engine_logic.py
import os, uuid
from qgis.core import (
    QgsProcessingAlgorithm, QgsProcessingParameterExtent,
    QgsProcessingParameterNumber, QgsProcessingParameterString, QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum, QgsProcessingParameterFolderDestination, QgsProcessingUtils,
    QgsProcessingException, QgsApplication, Qgis, QgsMessageLog, QgsTask
)
from qgis.PyQt.QtCore import QDate, Qt

# --- Date parameter compat (QGIS 3.34 doesn't have QgsProcessingParameterDate)
try:
    from qgis.core import QgsProcessingParameterDate  # type: ignore
    HAVE_DATE_PARAM = True
except Exception:
    QgsProcessingParameterDate = None  # type: ignore
    HAVE_DATE_PARAM = False


# Import VCubeProcessor from installed 'virtughan' (module 'vcube')
VCUBE_IMPORT_ERROR = None
try:
    from vcube.engine import VCubeProcessor
except Exception as e:
    VCubeProcessor = None  # type: ignore
    VCUBE_IMPORT_ERROR = e


def _coerce_to_qdate(val) -> QDate:
    """Accept QDate or ISO string 'YYYY-MM-DD'; return QDate (may be invalid)."""
    if isinstance(val, QDate):
        return val
    s = "" if val is None else str(val).strip()
    if not s:
        return QDate()
    qd = QDate.fromString(s, Qt.ISODate)  # expects YYYY-MM-DD
    return qd


class _VCubeTask(QgsTask):
    def __init__(self, desc, params):
        super().__init__(desc, QgsTask.CanCancel)
        self.params = params
        self.exc = None

    def run(self):
        try:
            log_path = os.path.join(self.params["output_dir"], "runtime.log")
            with open(log_path, "a", encoding="utf-8") as logf:
                proc = VCubeProcessor(
                    bbox=self.params["bbox"],
                    start_date=self.params["start_date"],
                    end_date=self.params["end_date"],
                    cloud_cover=self.params["cloud_cover"],
                    formula=self.params["formula"],
                    band1=self.params["band1"],
                    band2=self.params["band2"],
                    operation=self.params["operation"],
                    timeseries=self.params["timeseries"],
                    output_dir=self.params["output_dir"],
                    log_file=logf,
                    cmap=self.params.get("cmap", "RdYlGn"),
                    workers=self.params["workers"],
                    smart_filter=self.params.get("smart_filter", False),
                )
                proc.compute()
            return True
        except Exception as e:
            self.exc = e
            return False

    def finished(self, ok):
        if not ok or self.exc:
            QgsMessageLog.logMessage(str(self.exc), "VirtuGhan", Qgis.Critical)
        else:
            QgsMessageLog.logMessage("VirtuGhan Engine finished.", "VirtuGhan", Qgis.Info)


class VirtuGhanEngineAlgorithm(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterExtent("EXTENT", "Area of interest"))

        if HAVE_DATE_PARAM:
            self.addParameter(QgsProcessingParameterDate(
                "START_DATE", "Start date", defaultValue=QDate.currentDate().addYears(-1)
            ))
            self.addParameter(QgsProcessingParameterDate(
                "END_DATE", "End date", defaultValue=QDate.currentDate()
            ))
        else:
            # Fallback: users type YYYY-MM-DD (we'll parse it)
            self.addParameter(QgsProcessingParameterString(
                "START_DATE", "Start date (YYYY-MM-DD)", defaultValue=QDate.currentDate().addYears(-1).toString("yyyy-MM-dd")
            ))
            self.addParameter(QgsProcessingParameterString(
                "END_DATE", "End date (YYYY-MM-DD)", defaultValue=QDate.currentDate().toString("yyyy-MM-dd")
            ))

        self.addParameter(QgsProcessingParameterNumber(
            "CLOUD_COVER", "Max cloud cover (%)",
            type=QgsProcessingParameterNumber.Integer, defaultValue=30
        ))
        self.addParameter(QgsProcessingParameterString("FORMULA", "Formula", defaultValue="(band2-band1)/(band2+band1)"))
        self.addParameter(QgsProcessingParameterString("BAND1", "Band 1", defaultValue="red"))
        self.addParameter(QgsProcessingParameterString("BAND2", "Band 2 (optional)", defaultValue="nir"))
        self.addParameter(QgsProcessingParameterEnum(
            "OPERATION", "Aggregation",
            options=["mean","median","max","min","std","sum","var","none"], defaultValue=1
        ))
        self.addParameter(QgsProcessingParameterBoolean("TIMESERIES", "Generate timeseries", defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean("SMART_FILTER", "Apply smart filter", defaultValue=False))
        self.addParameter(QgsProcessingParameterNumber(
            "WORKERS", "Workers (0=auto)", type=QgsProcessingParameterNumber.Integer, defaultValue=0
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            "OUTPUT_FOLDER", "Output folder (blank = temp)", optional=True
        ))

    def name(self): return "virtughan_engine"
    def displayName(self): return "VirtuGhan Engine (VCube)"
    def group(self): return "VirtuGhan"
    def groupId(self): return "virtughan"
    def shortHelpString(self): return "Run VirtuGhan Engine (VCubeProcessor) from the Processing Toolbox."
    def createInstance(self): return VirtuGhanEngineAlgorithm()

    def processAlgorithm(self, parameters, context, feedback):
        if VCUBE_IMPORT_ERROR:
            raise QgsProcessingException(f"VCubeProcessor import failed: {VCUBE_IMPORT_ERROR}")

        extent = self.parameterAsExtent(parameters, "EXTENT", context)
        bbox = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]

        # Dates: works for both QDate param and string fallback
        if HAVE_DATE_PARAM:
            sd_q = self.parameterAsDate(parameters, "START_DATE", context)
            ed_q = self.parameterAsDate(parameters, "END_DATE", context)
        else:
            sd_q = _coerce_to_qdate(self.parameterAsString(parameters, "START_DATE", context))
            ed_q = _coerce_to_qdate(self.parameterAsString(parameters, "END_DATE", context))

        if not sd_q.isValid() or not ed_q.isValid():
            raise QgsProcessingException("Invalid date. Use YYYY-MM-DD.")

        s = sd_q.toString("yyyy-MM-dd")
        e = ed_q.toString("yyyy-MM-dd")

        cloud = int(self.parameterAsDouble(parameters, "CLOUD_COVER", context))
        formula = self.parameterAsString(parameters, "FORMULA", context)
        band1 = self.parameterAsString(parameters, "BAND1", context).strip()
        band2 = self.parameterAsString(parameters, "BAND2", context).strip() or None
        op_idx = self.parameterAsEnum(parameters, "OPERATION", context)
        ops = ["mean","median","max","min","std","sum","var","none"]
        operation = None if ops[op_idx] == "none" else ops[op_idx]
        ts = self.parameterAsBool(parameters, "TIMESERIES", context)
        smart = self.parameterAsBool(parameters, "SMART_FILTER", context)
        workers = int(self.parameterAsDouble(parameters, "WORKERS", context))
        if workers <= 0:
            try:
                import multiprocessing
                workers = max(1, multiprocessing.cpu_count() - 1)
            except Exception:
                workers = 1

        out_base = self.parameterAsString(parameters, "OUTPUT_FOLDER", context) or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(out_base, f"virtughan_engine_{uuid.uuid4().hex[:8]}")
        os.makedirs(out_dir, exist_ok=True)

        params = dict(
            bbox=bbox, start_date=s, end_date=e, cloud_cover=cloud,
            formula=formula, band1=band1, band2=band2,
            operation=operation, timeseries=ts,
            output_dir=out_dir, smart_filter=smart, workers=workers
        )

        feedback.pushInfo(f"Output: {out_dir}")
        task = _VCubeTask("VirtuGhan Engine", params)
        QgsApplication.taskManager().addTask(task)

        return {"OUTPUT": out_dir}
