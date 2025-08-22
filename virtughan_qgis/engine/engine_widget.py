# virtughan_qgis/engine/engine_widget.py
import os
import uuid
import traceback
from datetime import datetime

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QDate, QTimer
from qgis.PyQt.QtWidgets import (
    QWidget, QDockWidget, QFileDialog, QMessageBox,
    QProgressBar, QPlainTextEdit, QComboBox, QCheckBox, QLabel,
    QPushButton, QSpinBox, QLineEdit, QDateEdit, QFormLayout, QVBoxLayout
)

from qgis.core import (
    Qgis,
    QgsMessageLog,
    QgsProcessingUtils,
    QgsWkbTypes,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsRectangle,
    QgsRasterLayer,
    QgsApplication,
    QgsTask,
)
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand

# Try to import your reusable CommonParamsWidget
COMMON_IMPORT_ERROR = None
CommonParamsWidget = None
try:
    from ..common.common_widget import CommonParamsWidget
except Exception as _e:
    COMMON_IMPORT_ERROR = _e
    CommonParamsWidget = None

# Import VirtughanProcessor
VIRTUGHAN_IMPORT_ERROR = None
VirtughanProcessor = None
try:
    from virtughan.engine import VirtughanProcessor
except Exception as _e:
    VIRTUGHAN_IMPORT_ERROR = _e
    VirtughanProcessor = None

# Load UI
UI_PATH = os.path.join(os.path.dirname(__file__), "engine_form.ui")
FORM_CLASS, _ = uic.loadUiType(UI_PATH)


def _log(widget, msg, level=Qgis.Info):
    QgsMessageLog.logMessage(str(msg), "VirtuGhan", level)
    try:
        widget.logText.appendPlainText(str(msg))
    except Exception:
        pass


def _extent_to_wgs84_bbox(iface, extent):
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
    return [min(ll.x(), ur.x()), min(ll.y(), ur.y()), max(ll.x(), ur.x()), max(ll.y(), ur.y())]


def _bbox_looks_projected(b):
    return bool(b) and (abs(b[0]) > 180 or abs(b[2]) > 180 or abs(b[1]) > 90 or abs(b[3]) > 90)


def _rect_from_bbox(bbox):
    return QgsRectangle(bbox[0], bbox[1], bbox[2], bbox[3])


class _AoiDrawTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas, on_finished):
        super().__init__(canvas)
        self.canvas = canvas
        self.on_finished = on_finished
        self.points = []
        self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
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


class _VirtughanTask(QgsTask):
    """Runs VirtughanProcessor.compute() off the UI thread and writes to runtime.log."""
    def __init__(self, desc, params, log_path, on_done=None):
        super().__init__(desc, QgsTask.CanCancel)
        self.params = params
        self.log_path = log_path
        self.on_done = on_done
        self.exc = None

    def run(self):
        try:
            os.makedirs(self.params["output_dir"], exist_ok=True)

            # Minimal, Processing-like env
            os.environ.setdefault("GDAL_HTTP_TIMEOUT", "30")
            os.environ.setdefault("CPL_DEBUG", "ON")
            os.environ["CPL_LOG"] = self.log_path

            with open(self.log_path, "a", encoding="utf-8", buffering=1) as logf:
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] Starting VirtughanProcessor\n")
                logf.write(f"Params: {self.params}\n")

                proc = VirtughanProcessor(
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
                    cmap="RdYlGn",
                    workers=self.params["workers"],
                    smart_filter=self.params["smart_filter"],
                )
                proc.compute()
                logf.write("compute() finished.\n")
            return True
        except Exception as e:
            self.exc = e
            try:
                with open(self.log_path, "a", encoding="utf-8", buffering=1) as logf:
                    logf.write("[exception]\n")
                    logf.write(traceback.format_exc())
            except Exception:
                pass
            return False

    def finished(self, ok):
        # back on the main thread
        if self.on_done:
            try:
                self.on_done(ok, self.exc)
            except Exception:
                pass


class _UiLogTailer:
    """Polls a text file and appends new content to a QPlainTextEdit without blocking UI."""
    def __init__(self, log_path: str, log_widget: QPlainTextEdit, interval_ms: int = 400):
        self._path = log_path
        self._widget = log_widget
        self._pos = 0
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll_once)

    def start(self):
        # ensure file exists
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            open(self._path, "a", encoding="utf-8").close()
        except Exception:
            pass
        self._pos = 0
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll_once(self):
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                chunk = f.read()
                if chunk:
                    self._widget.appendPlainText(chunk.rstrip("\n"))
                    self._pos = f.tell()
        except Exception:
            # swallow polling errors; next tick may succeed
            pass


class EngineDockWidget(QDockWidget):
    def __init__(self, iface):
        super().__init__("VirtuGhan • Engine", iface.mainWindow())
        self.iface = iface
        self.setObjectName("VirtuGhanEngineDock")

        # Inflate UI
        self.ui_root = QWidget(self)
        self._form_owner = FORM_CLASS()
        self._form_owner.setupUi(self.ui_root)
        self.setWidget(self.ui_root)

        f = self.ui_root.findChild
        # Core controls
        self.progressBar        = f(QProgressBar, "progressBar")
        self.runButton          = f(QPushButton,   "runButton")
        self.resetButton        = f(QPushButton,   "resetButton")
        self.helpButton         = f(QPushButton,   "helpButton")
        self.logText            = f(QPlainTextEdit,"logText")
        # Common host (must exist in .ui)
        self.commonHost         = f(QWidget,       "commonParamsContainer")
        # AOI
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

        # Guard
        critical = {
            "progressBar": self.progressBar, "runButton": self.runButton,
            "resetButton": self.resetButton, "helpButton": self.helpButton,
            "logText": self.logText, "commonParamsContainer": self.commonHost,
            "aoiModeCombo": self.aoiModeCombo, "aoiUseCanvasButton": self.aoiUseCanvasButton,
            "aoiStartDrawButton": self.aoiStartDrawButton, "aoiClearButton": self.aoiClearButton,
            "aoiPreviewLabel": self.aoiPreviewLabel, "opCombo": self.opCombo,
            "timeseriesCheck": self.timeseriesCheck, "smartFilterCheck": self.smartFilterCheck,
            "workersSpin": self.workersSpin, "outputPathEdit": self.outputPathEdit,
            "outputBrowseButton": self.outputBrowseButton,
        }
        missing = [name for name, ref in critical.items() if ref is None]
        if missing:
            raise RuntimeError(f"Engine UI missing widgets: {', '.join(missing)}. "
                               f"Make sure engine_form.ui names match the code.")

        # Embed the CommonParamsWidget (or fallback)
        self._init_common_widget()

        # Initial UI state
        self.progressBar.setVisible(False)
        # Align with your updated UI defaults
        self.workersSpin.setMinimum(1)
        if self.workersSpin.value() < 1:
            self.workersSpin.setValue(1)

        # Wire buttons
        self.aoiUseCanvasButton.clicked.connect(self._use_canvas_extent)
        self.aoiStartDrawButton.clicked.connect(self._start_draw_aoi)
        self.aoiClearButton.clicked.connect(self._clear_aoi)
        self.aoiModeCombo.currentTextChanged.connect(self._aoi_mode_changed)

        self.outputBrowseButton.clicked.connect(self._browse_output)
        self.resetButton.clicked.connect(self._reset_form)
        self.runButton.clicked.connect(self._run_clicked)
        self.helpButton.clicked.connect(self._open_help)

        # AOI state
        self._aoi_bbox = None
        self._aoi_tool = None
        self._update_aoi_preview()
        self._aoi_mode_changed(self.aoiModeCombo.currentText())

        # Log tailer state
        self._tailer = None
        self._current_task = None
        self._current_log_path = None

    # ---------- Common panel ----------
    def _init_common_widget(self):
        host = self.commonHost
        v = QVBoxLayout(host); v.setContentsMargins(0, 0, 0, 0)

        if CommonParamsWidget is not None:
            self._common = CommonParamsWidget(host)
            try:
                self._common.set_defaults(
                    start_date=QDate.currentDate().addMonths(-1),
                    end_date=QDate.currentDate(),
                    cloud=30,
                    band1="red",
                    band2="nir",
                    formula="(band2-band1)/(band2+band1)",
                )
            except Exception:
                pass
            v.addWidget(self._common)
            _log(self, "Using CommonParamsWidget.", Qgis.Info)
        else:
            # Minimal fallback form
            fb = QWidget(host)
            form = QFormLayout(fb)
            self.fb_start = QDateEdit(fb); self.fb_start.setCalendarPopup(True); self.fb_start.setDate(QDate.currentDate().addMonths(-1))
            self.fb_end   = QDateEdit(fb); self.fb_end.setCalendarPopup(True);   self.fb_end.setDate(QDate.currentDate())
            self.fb_cloud = QSpinBox(fb);  self.fb_cloud.setRange(0,100); self.fb_cloud.setValue(30)
            self.fb_formula = QLineEdit("(band2-band1)/(band2+band1)", fb)
            self.fb_band1 = QLineEdit("red", fb)
            self.fb_band2 = QLineEdit("nir", fb)
            form.addRow("Start date", self.fb_start)
            form.addRow("End date", self.fb_end)
            form.addRow("Max cloud cover (%)", self.fb_cloud)
            form.addRow("Formula", self.fb_formula)
            form.addRow("Band 1", self.fb_band1)
            form.addRow("Band 2 (optional)", self.fb_band2)
            v.addWidget(fb)
            self._common = None
            _log(self, f"CommonParamsWidget not available: {COMMON_IMPORT_ERROR}", Qgis.Warning)

    def _get_common_params(self):
        if self._common is not None:
            return self._common.get_params()
        return {
            "start_date": self.fb_start.date().toString("yyyy-MM-dd"),
            "end_date": self.fb_end.date().toString("yyyy-MM-dd"),
            "cloud_cover": int(self.fb_cloud.value()),
            "band1": self.fb_band1.text().strip(),
            "band2": (self.fb_band2.text().strip() or None),
            "formula": self.fb_formula.text().strip(),
        }

    # ---------- Helpers ----------
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
        # Reset common
        if self._common is not None:
            try:
                self._common.set_defaults(
                    start_date=QDate.currentDate().addMonths(-1),
                    end_date=QDate.currentDate(),
                    cloud=30,
                    band1="red",
                    band2="nir",
                    formula="(band2-band1)/(band2+band1)",
                )
            except Exception:
                pass
        else:
            try:
                self.fb_start.setDate(QDate.currentDate().addMonths(-1))
                self.fb_end.setDate(QDate.currentDate())
                self.fb_cloud.setValue(30)
                self.fb_formula.setText("(band2-band1)/(band2+band1)")
                self.fb_band1.setText("red")
                self.fb_band2.setText("nir")
            except Exception:
                pass

        self._aoi_bbox = None
        self._update_aoi_preview()
        self.opCombo.setCurrentIndex(7)          # 'none'
        self.timeseriesCheck.setChecked(False)
        self.smartFilterCheck.setChecked(False)
        self.workersSpin.setMinimum(1)
        if self.workersSpin.value() < 1:
            self.workersSpin.setValue(1)
        self.outputPathEdit.clear()
        self.logText.clear()

    # ---------- AOI handling ----------
    def _aoi_mode_changed(self, text: str):
        t = (text or "").lower()
        self.aoiUseCanvasButton.setEnabled("extent" in t)
        self.aoiStartDrawButton.setEnabled("draw" in t)

    def _use_canvas_extent(self):
        canvas: QgsMapCanvas = self.iface.mapCanvas()
        if not canvas or not canvas.extent():
            QMessageBox.warning(self, "VirtuGhan", "No map canvas extent available.")
            return
        self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, canvas.extent())
        self._update_aoi_preview()

    def _start_draw_aoi(self):
        canvas: QgsMapCanvas = self.iface.mapCanvas()
        if not canvas:
            QMessageBox.warning(self, "VirtuGhan", "Map canvas not available.")
            return
        if "draw" not in (self.aoiModeCombo.currentText() or "").lower():
            self.aoiModeCombo.setCurrentText("Draw polygon")

        prev_tool = canvas.mapTool()

        def _finish(local_bbox):
            try:
                canvas.setMapTool(prev_tool)
            except Exception:
                pass
            if local_bbox is None:
                _log(self, "AOI drawing canceled.")
                return
            self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, _rect_from_bbox(local_bbox))
            self._update_aoi_preview()

        self._aoi_tool = _AoiDrawTool(canvas, _finish)
        canvas.setMapTool(self._aoi_tool)
        _log(self, "Drawing AOI: left-click to add vertices, right-click to finish, Esc to cancel.")

    def _clear_aoi(self):
        self._aoi_bbox = None
        self._update_aoi_preview()

    def _update_aoi_preview(self):
        if self._aoi_bbox:
            x1, y1, x2, y2 = self._aoi_bbox
            self.aoiPreviewLabel.setText(f"AOI (EPSG:4326): ({x1:.6f}, {y1:.6f}, {x2:.6f}, {y2:.6f})")
        else:
            self.aoiPreviewLabel.setText("<i>AOI: not set yet</i>")

    # ---------- Collect params ----------
    def _collect_params(self):
        if VirtughanProcessor is None:
            raise RuntimeError(f"VirtughanProcessor import failed: {VIRTUGHAN_IMPORT_ERROR}")
        if not self._aoi_bbox:
            raise RuntimeError("Please set AOI (Use Canvas Extent or Draw AOI) before running.")
        if _bbox_looks_projected(self._aoi_bbox):
            raise RuntimeError(f"AOI bbox does not look like EPSG:4326: {self._aoi_bbox}")

        p = self._get_common_params()
        # basic checks
        sdt = QDate.fromString(p["start_date"], "yyyy-MM-dd")
        edt = QDate.fromString(p["end_date"], "yyyy-MM-dd")
        if not sdt.isValid() or not edt.isValid():
            raise RuntimeError("Please pick valid start/end dates.")
        if sdt > edt:
            raise RuntimeError("Start date must be before end date.")
        if not p.get("formula"):
            raise RuntimeError("Formula is required.")
        if not p.get("band1"):
            raise RuntimeError("Band 1 is required.")

        op_txt = (self.opCombo.currentText() or "").strip()
        operation = None if op_txt == "none" else op_txt

        if (not self.timeseriesCheck.isChecked()) and (operation is None):
            raise RuntimeError("Operation is required when 'Generate timeseries' is disabled.")

        workers = max(1, int(self.workersSpin.value()))
        out_base = (self.outputPathEdit.text() or "").strip() or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(out_base, f"virtughan_engine_{uuid.uuid4().hex[:8]}")

        return dict(
            bbox=self._aoi_bbox,
            start_date=p["start_date"],
            end_date=p["end_date"],
            cloud_cover=int(p["cloud_cover"]),
            formula=p["formula"],
            band1=p["band1"],
            band2=p.get("band2") or None,
            operation=operation,
            timeseries=self.timeseriesCheck.isChecked(),
            smart_filter=self.smartFilterCheck.isChecked(),
            workers=workers,
            output_dir=out_dir,
        )

    # ---------- Log tailing ----------
    def _start_tailing(self, log_path: str):
        self._current_log_path = log_path
        self._tailer = _UiLogTailer(log_path, self.logText, interval_ms=400)
        self._tailer.start()

    def _stop_tailing(self):
        if self._tailer:
            self._tailer.stop()
            self._tailer = None
        self._current_log_path = None

    # ---------- Run (background via QgsTask) ----------
    def _run_clicked(self):
        try:
            params = self._collect_params()
        except Exception as e:
            QMessageBox.warning(self, "VirtuGhan", str(e))
            return

        out_dir = params["output_dir"]
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "VirtuGhan", f"Cannot create output folder:\n{out_dir}\n\n{e}")
            return

        log_path = os.path.join(out_dir, "runtime.log")
        _log(self, f"Output: {out_dir}")
        _log(self, f"Log file: {log_path}")

        # Create an empty log file so the tailer has something to open
        try:
            open(log_path, "a", encoding="utf-8").close()
        except Exception:
            pass

        self._set_running(True)
        self._start_tailing(log_path)

        def _on_done(ok, exc):
            # stop tailing first so we don't race with file close
            self._stop_tailing()
            self._set_running(False)
            if not ok or exc:
                _log(self, f"Engine failed: {exc}", Qgis.Critical)
                QMessageBox.critical(self, "VirtuGhan", f"Engine failed:\n{exc}\n\nSee runtime.log for details.")
            else:
                # Auto-load rasters
                added = 0
                for root, _dirs, files in os.walk(out_dir):
                    for fn in files:
                        if fn.lower().endswith((".tif", ".tiff", ".vrt")):
                            path = os.path.join(root, fn)
                            lyr = QgsRasterLayer(path, os.path.splitext(fn)[0], "gdal")
                            if lyr.isValid():
                                QgsProject.instance().addMapLayer(lyr)
                                _log(self, f"Loaded raster: {path}")
                                added += 1
                            else:
                                _log(self, f"Failed to load raster: {path}", Qgis.Warning)
                if added == 0:
                    _log(self, "No .tif/.tiff/.vrt files found to load.")
                QMessageBox.information(self, "VirtuGhan", f"Engine finished.\nOutput: {out_dir}")

        # Launch background task
        self._current_task = _VirtughanTask("VirtuGhan Engine", params, log_path, on_done=_on_done)
        QgsApplication.taskManager().addTask(self._current_task)

    def _set_running(self, running: bool):
        self.progressBar.setVisible(running)
        self.progressBar.setRange(0, 0 if running else 1)
        self.runButton.setEnabled(not running)
        self.resetButton.setEnabled(not running)
        for w in (self.aoiUseCanvasButton, self.aoiStartDrawButton, self.aoiClearButton,
                  self.aoiModeCombo, self.outputBrowseButton):
            try:
                w.setEnabled(not running)
            except Exception:
                pass
