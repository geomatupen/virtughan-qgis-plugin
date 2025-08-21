# virtughan_qgis/extractor/extractor_widget.py
import os, uuid, traceback
from datetime import datetime
from qgis.PyQt.QtWidgets import QVBoxLayout
from qgis.core import QgsWkbTypes

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QDate
from qgis.PyQt.QtWidgets import (
    QWidget, QDockWidget, QFileDialog, QMessageBox,QVBoxLayout,
    QProgressBar, QPlainTextEdit, QComboBox, QCheckBox, QLabel,
    QPushButton, QSpinBox, QLineEdit, QListWidget
)
from qgis.core import (
    Qgis, QgsMessageLog, QgsProcessingUtils, QgsProject,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsRectangle,
    QgsRasterLayer, QgsApplication, QgsTask
)
from qgis.gui import QgsMapTool, QgsRubberBand

# Import common parameters widget
COMMON_IMPORT_ERROR = None
CommonParamsWidget = None
try:
    from ..common.common_widget import CommonParamsWidget
except Exception as _e:
    COMMON_IMPORT_ERROR = _e
    CommonParamsWidget = None

# Backend
EXTRACTOR_IMPORT_ERROR = None
ExtractorBackend = None
try:
    from vcube.extract import ExtractProcessor as ExtractorBackend
except Exception as _e:
    EXTRACTOR_IMPORT_ERROR = _e
    ExtractorBackend = None

# Load UI
UI_PATH = os.path.join(os.path.dirname(__file__), "extractor_form.ui")
FORM_CLASS, _ = uic.loadUiType(UI_PATH)


def _log(widget, msg, level=Qgis.Info):
    QgsMessageLog.logMessage(str(msg), "VirtuGhan", level)
    try:
        widget.logText.appendPlainText(str(msg))
    except Exception:
        pass


# def _extent_to_wgs84_bbox(iface, extent):
#     if extent is None:
#         return None
#     canvas = iface.mapCanvas() if iface else None
#     src_crs = canvas.mapSettings().destinationCrs() if canvas else QgsProject.instance().crs()
#     wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
#     if not src_crs.isValid() or src_crs == wgs84:
#         return [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
#     xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
#     ll = xform.transform(extent.xMinimum(), extent.yMinimum())
#     ur = xform.transform(extent.xMaximum(), extent.yMaximum())
#     return [min(ll.x(), ur.x()), min(ll.y(), ur.y()), max(ll.x(), ur.x()), max(ll.y(), ur.y())]
def _extent_to_wgs84_bbox(iface, extent):
    if extent is None:
        return None

    canvas = iface.mapCanvas() if iface else None
    src_crs = canvas.mapSettings().destinationCrs() if canvas else QgsProject.instance().crs()
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())

    if isinstance(extent, QgsRectangle):
        # Rectangle AOI
        ll = xform.transform(extent.xMinimum(), extent.yMinimum())
        ur = xform.transform(extent.xMaximum(), extent.yMaximum())
        return [min(ll.x(), ur.x()), min(ll.y(), ur.y()), max(ll.x(), ur.x()), max(ll.y(), ur.y())]

    elif isinstance(extent, (list, tuple)) and all(hasattr(p, "x") for p in extent):
        # Polygon AOI as list of QgsPointXY
        transformed_points = [xform.transform(p) if hasattr(xform.transform(p), "x") else xform.transform(p.x(), p.y()) for p in extent]
        xs = [p.x() for p in transformed_points]
        ys = [p.y() for p in transformed_points]
        return [min(xs), min(ys), max(xs), max(ys)]

    else:
        raise TypeError("Unsupported AOI type: {}".format(type(extent)))



def _bbox_looks_projected(b):
    return bool(b) and (
        abs(b[0]) > 180 or abs(b[2]) > 180 or abs(b[1]) > 90 or abs(b[3]) > 90
    )


class _AoiDrawTool(QgsMapTool):
    def __init__(self, canvas, on_done):
        super().__init__(canvas)
        self.canvas = canvas
        self.on_done = on_done
        #self.rb = QgsRubberBand(canvas, True)
        self.rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rb.setStrokeColor(Qt.red)
        self.rb.setFillColor(Qt.transparent)
        self.rb.setWidth(2)
        self.points = []

    def canvasPressEvent(self, event):
        self.points.append(self.toMapCoordinates(event.pos()))
        self.rb.addPoint(self.points[-1], True)

    def canvasReleaseEvent(self, event):
        pass

    def canvasMoveEvent(self, event):
        pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.deactivate()
        # elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
        #     if len(self.points) >= 2:
        #         rect = QgsRectangle(self.points[0], self.points[-1])
        #         self.on_done(rect)
        #     self.deactivate()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if len(self.points) >= 3:  # polygon requires at least 3 points
                polygon = [p for p in self.points]
                self.on_done(polygon)
            self.deactivate()

    def deactivate(self):
        #self.rb.reset(True)
        self.rb.reset()
        self.canvas.unsetMapTool(self)
        del self


class _ExtractorTask(QgsTask):
    def __init__(self, desc, params, log_path, on_done=None):
        super().__init__(desc, QgsTask.CanCancel)
        self.params = params
        self.log_path = log_path
        self.on_done = on_done
        self.exc = None

    def run(self):
        try:
            os.makedirs(self.params["output_dir"], exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8", buffering=1) as logf:
                logf.write(f"[{datetime.now().isoformat(timespec='seconds')}] Starting Extractor\n")
                logf.write(f"Params: {self.params}\n")
                extr = ExtractorBackend(
                    bbox=self.params["bbox"],
                    start_date=self.params["start_date"],
                    end_date=self.params["end_date"],
                    cloud_cover=self.params["cloud_cover"],
                    bands_list=self.params["bands_list"],
                    output_dir=self.params["output_dir"],
                    log_file=logf,
                    workers=self.params["workers"],
                    zip_output=self.params["zip_output"],
                    smart_filter=self.params["smart_filter"]
                )
                extr.extract()
                logf.write("Extractor finished.\n")
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
        if self.on_done:
            try:
                self.on_done(ok, self.exc)
            except Exception:
                pass


class ExtractorDockWidget(QDockWidget):
    def __init__(self, iface):
        super().__init__("VirtuGhan • Extractor", iface.mainWindow())
        self.iface = iface
        self.setObjectName("VirtuGhanExtractorDock")

        self.ui_root = QWidget(self)
        self._form_owner = FORM_CLASS()
        self._form_owner.setupUi(self.ui_root)
        self.setWidget(self.ui_root)

        f = self.ui_root.findChild
        self.progressBar = f(QProgressBar, "progressBar")
        self.runButton = f(QPushButton, "runButton")
        self.resetButton = f(QPushButton, "resetButton")
        self.helpButton = f(QPushButton, "helpButton")
        self.logText = f(QPlainTextEdit, "logText")
        self.commonHost = f(QWidget, "commonParamsContainer")
        self.aoiModeCombo = f(QComboBox, "aoiModeCombo")
        self.aoiUseCanvasButton = f(QPushButton, "aoiUseCanvasButton")
        self.aoiStartDrawButton = f(QPushButton, "aoiStartDrawButton")
        self.aoiClearButton = f(QPushButton, "aoiClearButton")
        self.aoiPreviewLabel = f(QLabel, "aoiPreviewLabel")
        self.workersSpin = f(QSpinBox, "workersSpin")
        self.outputPathEdit = f(QLineEdit, "outputPathEdit")
        self.outputBrowseButton = f(QPushButton, "outputBrowseButton")

        # Extractor-specific widgets
        self.bandsListWidget = f(QListWidget, "bandsListWidget")
        self.zipOutputCheck = f(QCheckBox, "zipOutputCheck")
        self.smartFilterCheck = f(QCheckBox, "smartFilterCheck")

        # Init
        self._init_common_widget()
        self.progressBar.setVisible(False)
        if self.workersSpin.value() < 1:
            self.workersSpin.setValue(1)

        # Wire up
        self.aoiUseCanvasButton.clicked.connect(self._use_canvas_extent)
        self.aoiStartDrawButton.clicked.connect(self._start_draw_aoi)
        self.aoiClearButton.clicked.connect(self._clear_aoi)
        self.aoiModeCombo.currentTextChanged.connect(self._aoi_mode_changed)
        self.outputBrowseButton.clicked.connect(self._browse_output)
        self.resetButton.clicked.connect(self._reset_form)
        self.runButton.clicked.connect(self._run_clicked)
        self.helpButton.clicked.connect(self._open_help)

        self._aoi_bbox = None
        self._aoi_tool = None
        self._update_aoi_preview()

        self._tailer = None
        self._current_task = None
        self._current_log_path = None

    def _init_common_widget(self):
        if CommonParamsWidget:
            self.commonWidget = CommonParamsWidget(parent=self.commonHost)
            layout = self.commonHost.layout() or QVBoxLayout(self.commonHost)
            layout.addWidget(self.commonWidget)
        else:
            self.commonWidget = None
            _log(self, f"CommonParamsWidget failed: {COMMON_IMPORT_ERROR}", Qgis.Warning)

    def _get_common_params(self):
        if self.commonWidget:
            return self.commonWidget.get_params()
        return {}

    def _use_canvas_extent(self):
        extent = self.iface.mapCanvas().extent()
        self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, extent)
        self._update_aoi_preview()

    def _start_draw_aoi(self):
        self._aoi_tool = _AoiDrawTool(self.iface.mapCanvas(), self._draw_aoi_done)
        self.iface.mapCanvas().setMapTool(self._aoi_tool)

    def _draw_aoi_done(self, rect):
        self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, rect)
        self._update_aoi_preview()

    def _clear_aoi(self):
        self._aoi_bbox = None
        if self._aoi_tool:
            self._aoi_tool.deactivate()
            self._aoi_tool = None
        self._update_aoi_preview()
        #self._update_aoi_preview()

    def _aoi_mode_changed(self, text):
        pass  # no-op for now

    def _update_aoi_preview(self):
        if self._aoi_bbox:
            self.aoiPreviewLabel.setText(f"{self._aoi_bbox}")
        else:
            self.aoiPreviewLabel.setText("<i>AOI: not set yet</i>")

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.outputPathEdit.setText(folder)
    # def reset(self):
    #     # Reset all fields to default values
    #     self.startDateEdit.setDate(QDate.currentDate())
    #     self.endDateEdit.setDate(QDate.currentDate())
    #     self.cloudCoverSpin.setValue(100)

    def _reset_form(self):
        self._aoi_bbox = None
        self._update_aoi_preview()
        if self.commonWidget and hasattr(self.commonWidget, "reset"):
            self.commonWidget.reset()
            # self.bandsListWidget.clearSelection()
            # self.zipOutputCheck.setChecked(False)
            # self.smartFilterCheck.setChecked(True)
            # self.workersSpin.setValue(1)
            # self.outputPathEdit.clear()
            # self.logText.clear()
            # self.progressBar.setValue(0)
            # self.progressBar.setVisible(False)
        #if self.commonWidget:
            

    def _open_help(self):
        QMessageBox.information(self, "Help", "VirtuGhan Extractor Help coming soon.")

    def _collect_params(self):
        if ExtractorBackend is None:
            raise RuntimeError(f"Extractor backend import failed: {EXTRACTOR_IMPORT_ERROR}")
        if not self._aoi_bbox:
            raise RuntimeError("Please set AOI before running.")
        if _bbox_looks_projected(self._aoi_bbox):
            raise RuntimeError(f"AOI bbox does not look like EPSG:4326: {self._aoi_bbox}")

        p = self._get_common_params()
        sdt = QDate.fromString(p["start_date"], "yyyy-MM-dd")
        edt = QDate.fromString(p["end_date"], "yyyy-MM-dd")
        if not sdt.isValid() or not edt.isValid():
            raise RuntimeError("Please pick valid start/end dates.")
        if sdt > edt:
            raise RuntimeError("Start date must be before end date.")

        # Bands list
        selected_items = self.bandsListWidget.selectedItems()
        bands_list = [i.text().strip() for i in selected_items if i.text().strip()]
        if not bands_list:
            raise RuntimeError("Please select at least one band to extract.")

        zip_out = self.zipOutputCheck.isChecked()
        smart = self.smartFilterCheck.isChecked()

        workers = max(1, int(self.workersSpin.value()))
        out_base = (self.outputPathEdit.text() or "").strip() or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(out_base, f"virtughan_extractor_{uuid.uuid4().hex[:8]}")

        return dict(
            bbox=self._aoi_bbox,
            start_date=p["start_date"],
            end_date=p["end_date"],
            cloud_cover=int(p["cloud_cover"]),
            bands_list=bands_list,
            zip_output=zip_out,
            smart_filter=smart,
            workers=workers,
            output_dir=out_dir
        )

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
        try:
            open(log_path, "a", encoding="utf-8").close()
        except Exception:
            pass

        def _on_done(ok, exc):
            if not ok or exc:
                _log(self, f"Extractor failed: {exc}", Qgis.Critical)
                QMessageBox.critical(self, "VirtuGhan", f"Extractor failed:\n{exc}\n\nSee runtime.log for details.")
            else:
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
                    _log(self, "No raster files found to load.")
                QMessageBox.information(self, "VirtuGhan", f"Extractor finished.\nOutput: {out_dir}")

        self._current_task = _ExtractorTask("VirtuGhan Extractor", params, log_path, on_done=_on_done)
        QgsApplication.taskManager().addTask(self._current_task)
