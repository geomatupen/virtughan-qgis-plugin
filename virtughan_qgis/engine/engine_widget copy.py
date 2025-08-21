import os, uuid
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import QDate
from qgis.core import (
    QgsApplication, QgsProject, QgsRasterLayer, QgsRectangle, QgsTask,
    QgsProcessingUtils, Qgis, QgsMessageLog
)

# Import VCubeProcessor from installed package (pip install virtughan)
VCUBE_IMPORT_ERROR = None
try:
    from vcube.engine import VCubeProcessor
except Exception as e:
    VCubeProcessor = None
    VCUBE_IMPORT_ERROR = e

from virtughan_qgis.common.common_widget import CommonParamsWidget
from virtughan_qgis.common.common_logic import auto_workers

HERE = os.path.dirname(__file__)
FORM_PATH = os.path.join(HERE, "engine_form.ui")

class EngineDockWidget(QtWidgets.QDockWidget):
    """
    Expects in engine_form.ui (besides commonParamsContainer):
      aoiButton, opCombo, timeseriesCheck, smartFilterCheck,
      workersSpin, outputBrowseButton, outputPathEdit, runButton, logText
      (plus any extra you added like progressBar/helpButton/resetButton)
    """
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("VirtuGhan • Engine")
        self.widget = uic.loadUi(FORM_PATH)
        self.setWidget(self.widget)

        if VCUBE_IMPORT_ERROR:
            QtWidgets.QMessageBox.critical(
                self, "VirtuGhan",
                "VCubeProcessor could not be imported.\n"
                "Install the 'virtughan' package (module 'vcube') in QGIS Python.\n\n"
                f"{VCUBE_IMPORT_ERROR}"
            )
            self.setEnabled(False)
            return

        # Inject reusable common params panel
        self.common = CommonParamsWidget(self.widget)
        container = getattr(self.widget, "commonParamsContainer", None)
        if container and isinstance(container, QtWidgets.QWidget):
            layout = QtWidgets.QVBoxLayout(container)
            layout.setContentsMargins(0,0,0,0)
            layout.addWidget(self.common)
        else:
            # fallback: add on top if container missing
            self.widget.layout().insertWidget(0, self.common)

        # engine-specific defaults
        self.widget.workersSpin.setRange(0, 64)
        self.widget.workersSpin.setValue(0)  # auto by default
        self.widget.opCombo.clear()
        self.widget.opCombo.addItems(["mean","median","max","min","std","sum","var","none"])

        # Wire buttons
        self.widget.aoiButton.clicked.connect(self._use_canvas_extent)
        self.widget.outputBrowseButton.clicked.connect(self._pick_output_folder)
        self.widget.runButton.clicked.connect(self._run)

        # Optional: wire resolution warnings to message bar + log
        self.common.warn_resolution_if_needed(self._warn)

        self._aoi = None

    def _warn(self, msg):
        self._append_log(msg)
        self.iface.messageBar().pushWarning("VirtuGhan", msg)

    def _use_canvas_extent(self):
        rect: QgsRectangle = self.iface.mapCanvas().extent()
        self._aoi = [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()]
        # if your UI has a preview label, update it:
        if hasattr(self.widget, "aoiPreviewLabel"):
            self.widget.aoiPreviewLabel.setText(f"AOI: {self._aoi}")
        self._append_log(f"AOI set from canvas: {self._aoi}")

    def _pick_output_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.widget.outputPathEdit.setText(folder)

    def _run(self):
        if VCubeProcessor is None: return
        if not self._aoi:
            self._use_canvas_extent()

        # collect common params
        p = self.common.get_params()
        start_date = p["start_date"]
        end_date = p["end_date"]
        cloud_cover = p["cloud_cover"]
        band1 = p["band1"]
        band2 = p["band2"]
        formula = p["formula"]

        # engine-specific params
        op = self.widget.opCombo.currentText().strip()
        operation = None if op == "none" else op
        timeseries = self.widget.timeseriesCheck.isChecked()
        smart_filter = self.widget.smartFilterCheck.isChecked()

        workers = int(self.widget.workersSpin.value())
        if workers <= 0:
            workers = auto_workers()

        base_out = self.widget.outputPathEdit.text().strip() or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(base_out, f"virtughan_engine_{uuid.uuid4().hex[:8]}")
        os.makedirs(out_dir, exist_ok=True)

        params = dict(
            bbox=self._aoi, start_date=start_date, end_date=end_date, cloud_cover=cloud_cover,
            formula=formula, band1=band1, band2=band2, operation=operation,
            timeseries=timeseries, output_dir=out_dir, smart_filter=smart_filter,
            workers=workers, cmap="RdYlGn",
        )

        # Optional: show progress bar if you added it
        if hasattr(self.widget, "progressBar"):
            self.widget.progressBar.setRange(0,0)  # busy

        task = _VCubeTask("VirtuGhan Engine", params, self._on_ok, self._on_err)
        self._append_log("Task queued…")
        QgsApplication.taskManager().addTask(task)

    def _on_ok(self, out_dir):
        # hide progress
        if hasattr(self.widget, "progressBar"):
            self.widget.progressBar.setRange(0,1)
            self.widget.progressBar.setValue(1)

        added = []
        for fn in ("custom_band_output_aggregate.tif", "custom_band_output_aggregate_colormap.png"):
            p = os.path.join(out_dir, fn)
            if os.path.exists(p):
                r = QgsRasterLayer(p, fn)
                if r.isValid():
                    QgsProject.instance().addMapLayer(r)
                    added.append(fn)
        self._append_log(f"Finished. Added: {', '.join(added) if added else 'no layers'}")
        self.iface.messageBar().pushInfo("VirtuGhan", f"Engine finished → {out_dir}")

    def _on_err(self, out_dir, msg):
        if hasattr(self.widget, "progressBar"):
            self.widget.progressBar.setRange(0,1)
            self.widget.progressBar.setValue(0)
        self._append_log(f"Failed: {msg}")
        self.iface.messageBar().pushCritical("VirtuGhan", f"Engine failed (log in {out_dir})")

    def _append_log(self, txt):
        if getattr(self.widget, "logText", None):
            self.widget.logText.appendPlainText(txt)
        else:
            QgsMessageLog.logMessage(txt, "VirtuGhan", Qgis.Info)


class _VCubeTask(QgsTask):
    def __init__(self, desc, params, cb_ok, cb_err):
        super().__init__(desc, QgsTask.CanCancel)
        self.params = params
        self.cb_ok = cb_ok
        self.cb_err = cb_err
        self.exc = None

    def run(self):
        try:
            log_path = os.path.join(self.params["output_dir"], "runtime.log")
            with open(log_path, "a") as logf:
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
        if ok and not self.exc:
            self.cb_ok(self.params["output_dir"])
        else:
            self.cb_err(self.params["output_dir"], str(self.exc) if self.exc else "Unknown error")
