# virtughan_qgis/engine/engine_widget.py
import os
import uuid
from datetime import datetime

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QDate
from qgis.PyQt.QtWidgets import (
    QWidget, QDockWidget, QFileDialog, QMessageBox, QVBoxLayout, QFormLayout, QDateEdit,
    QSpinBox, QLineEdit, QPushButton, QProgressBar, QPlainTextEdit, QComboBox, QCheckBox, QLabel
)

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMessageLog,
    QgsProcessingUtils,
    QgsTask,
    QgsWkbTypes,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
)
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand

# ---- Try to import your reusable "Common" widget -----------------------------
COMMON_IMPORT_ERROR = None
CommonParamsWidget = None
try:
    from ..common.common_widget import CommonParamsWidget  # your reusable widget
except Exception as _e:
    COMMON_IMPORT_ERROR = _e
    CommonParamsWidget = None

# ---- Import the engine from the installed 'virtughan' package ----------------
VCUBE_IMPORT_ERROR = None
VCubeProcessor = None
try:
    from vcube.engine import VCubeProcessor
except Exception as _e:
    VCUBE_IMPORT_ERROR = _e
    VCubeProcessor = None

# ---- Load the UI file at runtime --------------------------------------------
UI_PATH = os.path.join(os.path.dirname(__file__), "engine_form.ui")
FORM_CLASS, _ = uic.loadUiType(UI_PATH)


def _log(widget, msg, level=Qgis.Info):
    QgsMessageLog.logMessage(str(msg), "VirtuGhan", level)
    try:
        widget.logText.appendPlainText(str(msg))
    except Exception:
        pass


# ---------- AOI / CRS helpers (kept local for now; can be moved to a common module later) ----------
def _extent_to_wgs84(iface, extent):
    """Return [xmin, ymin, xmax, ymax] in EPSG:4326 for the given QgsRectangle extent."""
    if extent is None:
        return None
    canvas = iface.mapCanvas() if iface else None
    src_crs = canvas.mapSettings().destinationCrs() if canvas else QgsProject.instance().crs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    if not src_crs.isValid() or src_crs == wgs84:
        return [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
    xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
    ll = xform.transform(extent.xMinimum(), extent.yMinimum())
    ur = xform.transform(extent.xMaximum(), extent.yMaximum())
    xmin = min(ll.x(), ur.x()); xmax = max(ll.x(), ur.x())
    ymin = min(ll.y(), ur.y()); ymax = max(ll.y(), ur.y())
    return [xmin, ymin, xmax, ymax]


def _rect_from_bbox(bbox):
    """Make a QgsRectangle from [xmin, ymin, xmax, ymax]."""
    return QgsRectangle(bbox[0], bbox[1], bbox[2], bbox[3])


def _bbox_looks_projected(b):
    """Heuristic: true if bbox values exceed lon/lat ranges."""
    if not b:
        return False
    return (abs(b[0]) > 180 or abs(b[2]) > 180 or abs(b[1]) > 90 or abs(b[3]) > 90)


class _VCubeTask(QgsTask):
    def __init__(self, desc, params, on_done=None):
        super().__init__(desc, QgsTask.CanCancel)
        self.params = params
        self.on_done = on_done
        self.exc = None

    def run(self):
        try:
            os.makedirs(self.params["output_dir"], exist_ok=True)
            log_path = os.path.join(self.params["output_dir"], "runtime.log")
            with open(log_path, "a", encoding="utf-8") as logf:
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] Starting VCubeProcessor\n")
                # Echo params for debugging
                logf.write(
                    "Params: "
                    f"bbox={self.params['bbox']}, "
                    f"start={self.params['start_date']}, end={self.params['end_date']}, "
                    f"cloud={self.params['cloud_cover']}, band1={self.params['band1']}, band2={self.params['band2']}, "
                    f"op={self.params['operation']}, timeseries={self.params['timeseries']}, "
                    f"workers={self.params['workers']}, smart_filter={self.params.get('smart_filter')}\n"
                )
                logf.flush()

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
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] Finished\n")
            return True
        except Exception as e:
            self.exc = e
            return False

    def finished(self, ok):
        if self.on_done:
            try:
                self.on_done(ok, self.exc)
            except Exception:
                pass
        if not ok or self.exc:
            QgsMessageLog.logMessage(str(self.exc), "VirtuGhan", Qgis.Critical)
        else:
            QgsMessageLog.logMessage("VirtuGhan Engine finished.", "VirtuGhan", Qgis.Info)


class _AoiDrawTool(QgsMapTool):
    """
    Simple polygon-draw tool:
      - Left-click to add vertices
      - Right-click (or double-click) to finish
      - ESC to cancel
    Calls `on_finished(bbox)` with [xmin, ymin, xmax, ymax] in the **canvas CRS** or None if cancelled.
    """
    def __init__(self, canvas: QgsMapCanvas, on_finished):
        super().__init__(canvas)
        self.canvas = canvas
        self.on_finished = on_finished
        self.points = []
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rb.setFillColor(self.rb.fillColor())   # use defaults
        self.rb.setStrokeColor(self.rb.strokeColor())
        self.rb.setWidth(2)

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pt = event.mapPoint()
            self.points.append(QgsPointXY(pt))
            self._update_rb()
        elif event.button() == Qt.RightButton:
            self._finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            # cancel
            self._cleanup()
            if self.on_finished:
                self.on_finished(None)

    def canvasDoubleClickEvent(self, event):
        self._finish()

    def _update_rb(self):
        self.rb.reset(QgsWkbTypes.PolygonGeometry)
        if len(self.points) >= 2:
            geom = QgsGeometry.fromPolygonXY([self.points])
            self.rb.setToGeometry(geom, None)

    def _finish(self):
        bbox = None
        if len(self.points) >= 3:
            geom = QgsGeometry.fromPolygonXY([self.points])
            env = geom.boundingBox()
            bbox = [env.xMinimum(), env.yMinimum(), env.xMaximum(), env.yMaximum()]
        self._cleanup()
        if self.on_finished:
            self.on_finished(bbox)

    def _cleanup(self):
        try:
            self.rb.reset(True)
        except Exception:
            pass
        self.points = []


class EngineDockWidget(QDockWidget):
    def __init__(self, iface):
        super().__init__("VirtuGhan • Engine", iface.mainWindow())
        self.iface = iface
        self.setObjectName("VirtuGhanEngineDock")

        # Inflate UI into a container
        self.ui_root = QWidget(self)
        self._form_owner = FORM_CLASS()
        self._form_owner.setupUi(self.ui_root)
        self.setWidget(self.ui_root)

        # ---- BIND ALL CONTROLS SAFELY VIA findChild ----
        f = self.ui_root.findChild
        self.progressBar        = f(QProgressBar, "progressBar")
        self.runButton          = f(QPushButton,   "runButton")
        self.resetButton        = f(QPushButton,   "resetButton")
        self.helpButton         = f(QPushButton,   "helpButton")
        self.logText            = f(QPlainTextEdit,"logText")
        self.commonHost         = f(QWidget,       "commonParamsContainer")

        # AOI bits
        self.aoiModeCombo       = f(QComboBox,     "aoiModeCombo")
        self.aoiUseCanvasButton = f(QPushButton,   "aoiUseCanvasButton")
        self.aoiStartDrawButton = f(QPushButton,   "aoiStartDrawButton")
        self.aoiClearButton     = f(QPushButton,   "aoiClearButton")
        self.aoiPreviewLabel    = f(QLabel,        "aoiPreviewLabel")

        # Options / output
        self.opCombo            = f(QComboBox,     "opCombo")
        self.timeseriesCheck    = f(QCheckBox,     "timeseriesCheck")
        self.smartFilterCheck   = f(QCheckBox,     "smartFilterCheck")
        self.workersSpin        = f(QSpinBox,      "workersSpin")
        self.outputPathEdit     = f(QLineEdit,     "outputPathEdit")
        self.outputBrowseButton = f(QPushButton,   "outputBrowseButton")

        # Guard: critical widgets must exist
        critical = {
            "progressBar": self.progressBar, "runButton": self.runButton,
            "resetButton": self.resetButton, "logText": self.logText,
            "commonParamsContainer": self.commonHost, "opCombo": self.opCombo,
            "aoiModeCombo": self.aoiModeCombo, "aoiUseCanvasButton": self.aoiUseCanvasButton,
            "aoiStartDrawButton": self.aoiStartDrawButton, "aoiClearButton": self.aoiClearButton,
            "aoiPreviewLabel": self.aoiPreviewLabel,
        }
        missing = [name for name, ref in critical.items() if ref is None]
        if missing:
            raise RuntimeError(f"Engine UI missing widgets: {', '.join(missing)}. "
                               f"Make sure engine_form.ui names match the code.")

        # Initial UI state
        self.progressBar.setVisible(False)

        # Wire buttons
        self.aoiUseCanvasButton.clicked.connect(self._use_canvas_extent)
        self.aoiStartDrawButton.clicked.connect(self._start_draw_aoi)
        self.aoiClearButton.clicked.connect(self._clear_aoi)
        self.aoiModeCombo.currentTextChanged.connect(self._aoi_mode_changed)

        self.outputBrowseButton.clicked.connect(self._browse_output)
        self.resetButton.clicked.connect(self._reset_form)
        self.runButton.clicked.connect(self._run_clicked)
        self.helpButton.clicked.connect(self._open_help)

        # Embed common widget
        self._init_common_widget()

        # AOI state
        self._aoi_bbox = None  # ALWAYS store in EPSG:4326
        self._aoi_tool = None
        self._update_aoi_preview()
        self._aoi_mode_changed(self.aoiModeCombo.currentText())

    # ---------- UI helpers ----------
    def _init_common_widget(self):
        if CommonParamsWidget is None:
            # Fallback simple form directly in the host
            fallback = QWidget(self.commonHost)
            lay = QFormLayout(fallback)

            self.startDateEdit = QDateEdit(fallback); self.startDateEdit.setCalendarPopup(True)
            self.startDateEdit.setDate(QDate.currentDate().addYears(-1))
            self.endDateEdit = QDateEdit(fallback); self.endDateEdit.setCalendarPopup(True)
            self.endDateEdit.setDate(QDate.currentDate())

            self.cloudSpinFallback = QSpinBox(fallback); self.cloudSpinFallback.setRange(0, 100); self.cloudSpinFallback.setValue(30)
            self.formulaEditFallback = QLineEdit("(band2-band1)/(band2+band1)", fallback)
            self.band1EditFallback = QLineEdit("red", fallback)
            self.band2EditFallback = QLineEdit("nir", fallback)

            lay.addRow("Start date", self.startDateEdit)
            lay.addRow("End date", self.endDateEdit)
            lay.addRow("Max cloud cover (%)", self.cloudSpinFallback)
            lay.addRow("Formula", self.formulaEditFallback)
            lay.addRow("Band 1", self.band1EditFallback)
            lay.addRow("Band 2 (optional)", self.band2EditFallback)

            host = self.commonHost
            v = QVBoxLayout(host); v.setContentsMargins(0, 0, 0, 0); v.addWidget(fallback)

            _log(self, f"Common widget fallback active: {COMMON_IMPORT_ERROR}", Qgis.Warning)
            self._common = None
        else:
            host = self.commonHost
            v = QVBoxLayout(host); v.setContentsMargins(0, 0, 0, 0)
            self._common = CommonParamsWidget(host)
            # surface GSD mismatch warnings to the user
            self._common.warn_resolution_if_needed(lambda m: QMessageBox.warning(self, "VirtuGhan", m))
            v.addWidget(self._common)

    def _open_help(self):
        try:
            self.iface.openURL("https://example.com/virtughan-docs")
        except Exception:
            QMessageBox.information(self, "VirtuGhan", "Documentation URL not configured yet.")

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self.outputPathEdit.setText(path)

    def _reset_form(self):
        self._aoi_bbox = None
        self._update_aoi_preview()
        try:
            if self._common:
                self._common.set_defaults()
            else:
                self.startDateEdit.setDate(QDate.currentDate().addYears(-1))
                self.endDateEdit.setDate(QDate.currentDate())
                self.cloudSpinFallback.setValue(30)
                self.formulaEditFallback.setText("(band2-band1)/(band2+band1)")
                self.band1EditFallback.setText("red")
                self.band2EditFallback.setText("nir")
        except Exception:
            pass
        self.opCombo.setCurrentIndex(0)
        self.timeseriesCheck.setChecked(True)
        self.smartFilterCheck.setChecked(False)
        self.workersSpin.setValue(0)
        self.outputPathEdit.clear()
        self.logText.clear()

    # ---------- AOI handling ----------
    def _aoi_mode_changed(self, text: str):
        mode = (text or "").lower()
        using_extent = "extent" in mode
        using_draw = "draw" in mode
        self.aoiUseCanvasButton.setEnabled(using_extent)
        self.aoiStartDrawButton.setEnabled(using_draw)

    def _use_canvas_extent(self):
        canvas: QgsMapCanvas = self.iface.mapCanvas()
        if not canvas or not canvas.extent():
            QMessageBox.warning(self, "VirtuGhan", "No map canvas extent available.")
            return
        e = canvas.extent()
        # Always convert to WGS84 when storing
        self._aoi_bbox = _extent_to_wgs84(self.iface, e)
        self._update_aoi_preview()

    def _start_draw_aoi(self):
        canvas: QgsMapCanvas = self.iface.mapCanvas()
        if not canvas:
            QMessageBox.warning(self, "VirtuGhan", "Map canvas not available.")
            return

        # Ensure mode allows drawing
        if "draw" not in (self.aoiModeCombo.currentText() or "").lower():
            self.aoiModeCombo.setCurrentText("Draw polygon")

        prev_tool = canvas.mapTool()

        def _finish(bbox):
            # restore previous tool
            try:
                canvas.setMapTool(prev_tool)
            except Exception:
                pass
            if bbox is None:
                _log(self, "AOI drawing canceled.")
                return
            # bbox is in canvas CRS; convert to WGS84 before storing
            wgs_bbox = _extent_to_wgs84(self.iface, _rect_from_bbox(bbox))
            self._aoi_bbox = wgs_bbox
            self._update_aoi_preview()

        self._aoi_tool = _AoiDrawTool(canvas, _finish)
        canvas.setMapTool(self._aoi_tool)
        _log(self, "Drawing AOI: left-click to add vertices, right-click to finish, Esc to cancel.")

    def _clear_aoi(self):
        self._aoi_bbox = None
        self._update_aoi_preview()

    def _update_aoi_preview(self):
        if self._aoi_bbox:
            xmin, ymin, xmax, ymax = self._aoi_bbox
            self.aoiPreviewLabel.setText(f"AOI (EPSG:4326): ({xmin:.6f}, {ymin:.6f}, {xmax:.6f}, {ymax:.6f})")
        else:
            self.aoiPreviewLabel.setText("<i>AOI: not set yet</i>")

    # ---------- run ----------
    def _collect_params(self):
        if VCubeProcessor is None:
            raise RuntimeError(f"VCubeProcessor import failed: {VCUBE_IMPORT_ERROR}")
        if not self._aoi_bbox:
            raise RuntimeError("Please set AOI (Use Canvas Extent or Draw AOI) before running.")

        # Safety net: if stored bbox looks projected, try converting current canvas extent
        bbox_wgs84 = self._aoi_bbox
        if _bbox_looks_projected(bbox_wgs84):
            canvas = self.iface.mapCanvas()
            if canvas and canvas.extent():
                bbox_wgs84 = _extent_to_wgs84(self.iface, canvas.extent())
            else:
                raise RuntimeError("AOI appears to be in a projected CRS. Please set AOI again.")

        if self._common:
            c = self._common.get_params()
            start_date = c["start_date"]
            end_date   = c["end_date"]
            if start_date > end_date:
                raise RuntimeError("Start date must be before end date.")
            cloud      = c["cloud_cover"]
            band1      = c["band1"]
            band2      = c["band2"]
            formula    = c["formula"]
            if not formula:
                raise RuntimeError("Formula is required.")
            if not band1:
                raise RuntimeError("Band 1 is required.")
        else:
            sdt = self.startDateEdit.date()
            edt = self.endDateEdit.date()
            if not sdt.isValid() or not edt.isValid():
                raise RuntimeError("Please pick valid start/end dates.")
            if sdt > edt:
                raise RuntimeError("Start date must be before end date.")
            cloud = int(self.cloudSpinFallback.value())
            if cloud < 0 or cloud > 100:
                raise RuntimeError("Cloud cover must be between 0–100.")
            formula = self.formulaEditFallback.text().strip()
            band1 = self.band1EditFallback.text().strip()
            band2 = (self.band2EditFallback.text().strip() or None)
            if not formula:
                raise RuntimeError("Formula is required.")
            if not band1:
                raise RuntimeError("Band 1 is required.")
            start_date = sdt.toString("yyyy-MM-dd")
            end_date   = edt.toString("yyyy-MM-dd")

        op = (self.opCombo.currentText() or "").strip()
        operation = None if op == "none" else op

        workers = int(self.workersSpin.value())
        out_base = self.outputPathEdit.text().strip() or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(out_base, f"virtughan_engine_{uuid.uuid4().hex[:8]}")

        return dict(
            bbox=bbox_wgs84,
            start_date=start_date,
            end_date=end_date,
            cloud_cover=cloud,
            formula=formula,
            band1=band1,
            band2=band2,
            operation=operation,
            timeseries=self.timeseriesCheck.isChecked(),
            smart_filter=self.smartFilterCheck.isChecked(),
            workers=workers,
            output_dir=out_dir,
        )

    def _run_clicked(self):
        # Quick date order check when using common widget
        if self._common:
            try:
                p = self._common.get_params()
                if p["start_date"] > p["end_date"]:
                    QMessageBox.warning(self, "VirtuGhan", "Start date must be before end date.")
                    return
            except Exception:
                pass

        self._set_running(True)
        try:
            params = self._collect_params()
        except Exception as e:
            self._set_running(False)
            QMessageBox.warning(self, "VirtuGhan", str(e))
            return

        _log(self, f"Output: {params['output_dir']}")
        _log_path = os.path.join(params["output_dir"], "runtime.log")
        _log(self, f"Log file: {_log_path}")
        _log(self, "Submitting background task…")

        def _on_done(ok, exc):
            self._set_running(False)
            if not ok or exc:
                _log(self, f"Engine failed: {exc}", Qgis.Critical)
                QMessageBox.critical(self, "VirtuGhan", f"Engine failed:\n{exc}")
            else:
                _log(self, "Engine finished successfully.", Qgis.Info)
                QMessageBox.information(self, "VirtuGhan", "Engine finished.\n"
                                         f"Output: {params['output_dir']}")

        task = _VCubeTask("VirtuGhan Engine", params, on_done=_on_done)
        QgsApplication.taskManager().addTask(task)

    def _set_running(self, running: bool):
        self.progressBar.setVisible(running)
        self.progressBar.setRange(0, 0 if running else 1)
        self.runButton.setEnabled(not running)
        self.resetButton.setEnabled(not running)

        self.aoiUseCanvasButton.setEnabled(not running)
        self.aoiStartDrawButton.setEnabled(not running)
        self.aoiClearButton.setEnabled(not running)
        self.aoiModeCombo.setEnabled(not running)

        self.outputBrowseButton.setEnabled(not running)
