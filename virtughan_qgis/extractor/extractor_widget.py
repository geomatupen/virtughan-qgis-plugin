import os
import traceback
import uuid
from datetime import datetime

from osgeo import gdal, osr
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsProcessingUtils,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsTask,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

COMMON_IMPORT_ERROR = None
CommonParamsWidget = None
try:
    from ..common.common_widget import CommonParamsWidget
except Exception as _e:
    COMMON_IMPORT_ERROR = _e
    CommonParamsWidget = None


EXTRACTOR_IMPORT_ERROR = None
ExtractorBackend = None

from virtughan.extract import ExtractProcessor as ExtractorBackend

UI_PATH = os.path.join(os.path.dirname(__file__), "extractor_form.ui")
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
    src_crs = (
        canvas.mapSettings().destinationCrs() if canvas else QgsProject.instance().crs()
    )
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())

    if isinstance(extent, QgsRectangle):
        ll = xform.transform(extent.xMinimum(), extent.yMinimum())
        ur = xform.transform(extent.xMaximum(), extent.yMaximum())
        return [
            min(ll.x(), ur.x()),
            min(ll.y(), ur.y()),
            max(ll.x(), ur.x()),
            max(ll.y(), ur.y()),
        ]

    if isinstance(extent, QgsGeometry):
        try:
            poly = extent.asPolygon()
            if not poly:
                poly = extent.asMultiPolygon()[0] if extent.asMultiPolygon() else []
            points = poly[0] if poly else []
        except Exception:
            points = []
        pts = [p for p in points if hasattr(p, "x")]
        if not pts:
            raise TypeError("Geometry does not contain polygon points.")
        transformed = [xform.transform(p.x(), p.y()) for p in pts]
        xs = [p.x() for p in transformed]
        ys = [p.y() for p in transformed]
        return [min(xs), min(ys), max(xs), max(ys)]

    if isinstance(extent, (list, tuple)) and all(hasattr(p, "x") for p in extent):
        transformed = [xform.transform(p.x(), p.y()) for p in extent]
        xs = [p.x() for p in transformed]
        ys = [p.y() for p in transformed]
        return [min(xs), min(ys), max(xs), max(ys)]

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
        self.points = []
        self.rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        try:
            self.rb.setColor(QColor(255, 0, 0, 120))
            self.rb.setFillColor(QColor(255, 0, 0, 40))
        except Exception:
            try:
                self.rb.setStrokeColor(QColor(255, 0, 0, 120))
            except Exception:
                pass
        self.rb.setWidth(2)
        self._moving_point = None

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pt = self.toMapCoordinates(event.pos())
            pxy = QgsPointXY(pt)
            self.points.append(pxy)
            self.rb.addPoint(pxy, True)
        elif event.button() == Qt.RightButton:
            self._finish_polygon_and_emit()

    def canvasDoubleClickEvent(self, event):
        self._finish_polygon_and_emit()

    def canvasMoveEvent(self, event):
        if not self.points:
            return
        pt = self.toMapCoordinates(event.pos())
        try:
            if self._moving_point:
                self.rb.reset(QgsWkbTypes.PolygonGeometry)
                for p in self.points:
                    self.rb.addPoint(p, True)
            self._moving_point = QgsPointXY(pt)
            self.rb.addPoint(self._moving_point, True)
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.deactivate()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._finish_polygon_and_emit()

    def _finish_polygon_and_emit(self):
        if len(self.points) >= 3:
            poly_pts = list(self.points)
            if poly_pts[0] != poly_pts[-1]:
                poly_pts.append(poly_pts[0])
            polygon_geom = QgsGeometry.fromPolygonXY([poly_pts])
            xs = [p.x() for p in poly_pts]
            ys = [p.y() for p in poly_pts]
            rect = QgsRectangle(min(xs), min(ys), max(xs), max(ys))
            try:
                self.on_done(rect, polygon_geom)
            except Exception:
                pass
        self.deactivate()

    def deactivate(self):
        try:
            self.rb.reset(QgsWkbTypes.PolygonGeometry)
        except Exception:
            try:
                self.rb.reset()
            except Exception:
                pass
        try:
            self.canvas.unsetMapTool(self)
        except Exception:
            pass
        self.points = []
        self._moving_point = None


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
                logf.write(
                    f"[{datetime.now().isoformat(timespec='seconds')}] Starting Extractor\n"
                )
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
                    smart_filter=self.params["smart_filter"],
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

        self.bandsListWidget = f(QListWidget, "bandsListWidget")
        self.zipOutputCheck = f(QCheckBox, "zipOutputCheck")
        self.smartFilterCheck = f(QCheckBox, "smartFilterCheck")

        self._aoi_bbox = None
        self._aoi_polygon = None
        self._aoi_rect_mapcrs = None
        self._aoi_tool = None
        self._debug_bbox_rb = None

        self._init_common_widget()
        self.progressBar.setVisible(False)
        if self.workersSpin.value() < 1:
            self.workersSpin.setValue(1)

        self.aoiUseCanvasButton.clicked.connect(self._use_canvas_extent)
        self.aoiStartDrawButton.clicked.connect(self._start_draw_aoi)
        self.aoiClearButton.clicked.connect(self._clear_aoi)
        self.aoiModeCombo.currentTextChanged.connect(self._aoi_mode_changed)
        self.outputBrowseButton.clicked.connect(self._browse_output)
        self.resetButton.clicked.connect(self._reset_form)
        self.runButton.clicked.connect(self._run_clicked)
        self.helpButton.clicked.connect(self._open_help)

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
            _log(
                self, f"CommonParamsWidget failed: {COMMON_IMPORT_ERROR}", Qgis.Warning
            )

    def _get_common_params(self):
        if self.commonWidget:
            return self.commonWidget.get_params()
        return {}

    def _use_canvas_extent(self):
        canvas = self.iface.mapCanvas()
        extent_map = canvas.extent()
        self._aoi_rect_mapcrs = extent_map
        try:
            self._aoi_polygon = QgsGeometry.fromRect(extent_map)
        except Exception:
            self._aoi_polygon = None
        self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, extent_map)
        self._update_aoi_preview()
        _log(self, f"Using canvas extent for AOI: {self._aoi_bbox}")
        self._draw_debug_bbox(self._aoi_bbox)

    def _start_draw_aoi(self):
        self._aoi_tool = _AoiDrawTool(self.iface.mapCanvas(), self._draw_aoi_done)
        self.iface.mapCanvas().setMapTool(self._aoi_tool)

    def _draw_aoi_done(self, rect_mapcrs, polygon_geom_mapcrs):
        self._aoi_polygon = polygon_geom_mapcrs
        self._aoi_rect_mapcrs = rect_mapcrs

        self._aoi_bbox = _extent_to_wgs84_bbox(self.iface, rect_mapcrs)

        try:
            canvas = self.iface.mapCanvas()
            src_crs = canvas.mapSettings().destinationCrs()
            dst_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

            pts = []
            geom_poly = polygon_geom_mapcrs.asPolygon()
            if not geom_poly:
                geom_poly = (
                    polygon_geom_mapcrs.asMultiPolygon()[0]
                    if polygon_geom_mapcrs.asMultiPolygon()
                    else []
                )
            ring = geom_poly[0] if geom_poly else []
            for p in ring:
                tp = xform.transform(p.x(), p.y())
                pts.append([float(tp.x()), float(tp.y())])
            self._aoi_polygon_wgs84 = pts
        except Exception:
            self._aoi_polygon_wgs84 = None

        self._update_aoi_preview()
        try:
            vcount = len(polygon_geom_mapcrs.asPolygon()[0])
        except Exception:
            vcount = "?"
        _log(self, f"AOI polygon set (vertices: {vcount})")
        _log(self, f"AOI bbox (WGS84): {self._aoi_bbox}")
        self._draw_debug_bbox(self._aoi_bbox)
        if self._aoi_tool:
            try:
                self._aoi_tool.deactivate()
            except Exception:
                pass
            self._aoi_tool = None

    def _clear_aoi(self):
        self._aoi_bbox = None
        self._aoi_polygon = None
        self._aoi_rect_mapcrs = None
        if self._aoi_tool:
            try:
                self._aoi_tool.deactivate()
            except Exception:
                pass
            self._aoi_tool = None
        self._update_aoi_preview("AOI: not set yet")
        if getattr(self, "_debug_bbox_rb", None):
            try:
                self._debug_bbox_rb.reset(QgsWkbTypes.PolygonGeometry)
            except Exception:
                try:
                    self._debug_bbox_rb.reset()
                except Exception:
                    pass
            self._debug_bbox_rb = None

    def _aoi_mode_changed(self, text):
        pass

    def _update_aoi_preview(self, text=None):
        if text:
            self.aoiPreviewLabel.setText(text)
            return
        if self._aoi_bbox:
            bbox = self._aoi_bbox
            if self._aoi_polygon:
                try:
                    vcount = len(self._aoi_polygon.asPolygon()[0])
                except Exception:
                    vcount = "?"
                self.aoiPreviewLabel.setText(
                    f"AOI polygon set ({vcount} pts) — BBOX {bbox[0]:.6f}, {bbox[1]:.6f}, {bbox[2]:.6f}, {bbox[3]:.6f}"
                )
            else:
                self.aoiPreviewLabel.setText(
                    f"AOI BBOX {bbox[0]:.6f}, {bbox[1]:.6f}, {bbox[2]:.6f}, {bbox[3]:.6f}"
                )
        else:
            self.aoiPreviewLabel.setText("<i>AOI: not set yet</i>")

    def _draw_debug_bbox(self, bbox_wgs84):
        try:
            if getattr(self, "_debug_bbox_rb", None):
                try:
                    self._debug_bbox_rb.reset(QgsWkbTypes.PolygonGeometry)
                except Exception:
                    try:
                        self._debug_bbox_rb.reset()
                    except Exception:
                        pass
                self._debug_bbox_rb = None

            if not bbox_wgs84:
                return

            canvas = self.iface.mapCanvas()
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            dst_crs = canvas.mapSettings().destinationCrs()
            xform_back = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

            xmin, ymin, xmax, ymax = bbox_wgs84
            corners_wgs84 = [
                QgsPointXY(xmin, ymin),
                QgsPointXY(xmin, ymax),
                QgsPointXY(xmax, ymax),
                QgsPointXY(xmax, ymin),
                QgsPointXY(xmin, ymin),
            ]
            corners_map = []
            for pt in corners_wgs84:
                pmap = xform_back.transform(pt.x(), pt.y())
                corners_map.append(QgsPointXY(pmap.x(), pmap.y()))

            rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
            try:
                rb.setColor(QColor(0, 0, 255, 80))
            except Exception:
                try:
                    rb.setStrokeColor(QColor(0, 0, 255, 80))
                except Exception:
                    pass
            try:
                rb.setFillColor(QColor(0, 0, 255, 30))
            except Exception:
                pass
            rb.setWidth(2)
            for p in corners_map:
                rb.addPoint(p, True)

            self._debug_bbox_rb = rb

        except Exception as e:
            _log(self, f"_draw_debug_bbox failed: {e}", Qgis.Warning)

    def _inspect_raster(self, path):
        try:
            ds = gdal.Open(path)
            if ds is None:
                return None
            gt = ds.GetGeoTransform()
            w = ds.RasterXSize
            h = ds.RasterYSize
            prj = ds.GetProjection() or ""
            minx = gt[0]
            maxy = gt[3]
            maxx = gt[0] + gt[1] * w + gt[2] * h
            miny = gt[3] + gt[4] * w + gt[5] * h
            ds = None
            return {
                "path": path,
                "geoTransform": gt,
                "width": w,
                "height": h,
                "bbox": (minx, miny, maxx, maxy),
                "proj_wkt": prj,
            }
        except Exception as e:
            _log(self, f"_inspect_raster error: {e}", Qgis.Warning)
            return None

    def _rewrite_bounds_to_wgs84(self, src_path, bbox_wgs84):
        try:
            ds = gdal.Open(src_path)
            if ds is None:
                _log(
                    self,
                    f"_rewrite_bounds_to_wgs84: gdal.Open failed for {src_path}",
                    Qgis.Warning,
                )
                return None

            w = ds.RasterXSize
            h = ds.RasterYSize
            if not (w and h):
                _log(
                    self,
                    f"_rewrite_bounds_to_wgs84: invalid raster size for {src_path}",
                    Qgis.Warning,
                )
                ds = None
                return None

            xmin, ymin, xmax, ymax = bbox_wgs84
            px = (xmax - xmin) / float(w)
            py = (ymax - ymin) / float(h)
            geot = (xmin, px, 0.0, ymax, 0.0, -py)

            driver = gdal.GetDriverByName("GTiff")
            dst = src_path.replace(".tif", "_fixed.tif")
            try:
                if os.path.exists(dst):
                    os.remove(dst)
            except Exception:
                pass

            out_ds = driver.CreateCopy(dst, ds, strict=0)
            if out_ds is None:
                _log(
                    self,
                    f"_rewrite_bounds_to_wgs84: CreateCopy failed for {src_path}",
                    Qgis.Warning,
                )
                ds = None
                return None

            out_ds.SetGeoTransform(geot)

            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            out_ds.SetProjection(srs.ExportToWkt())

            out_ds.FlushCache()
            out_ds = None
            ds = None

            return dst

        except Exception as e:
            _log(self, f"_rewrite_bounds_to_wgs84 error: {e}", Qgis.Warning)
            return None

    def _try_fix_and_load(self, path, expected_bbox_wgs84):
        try:
            info = self._inspect_raster(path)
            if not info:
                _log(self, f"Could not inspect raster: {path}", Qgis.Warning)
                return False

            if "EPSG:4326" in (info["proj_wkt"] or ""):
                load_path = path
            else:
                try:
                    from pyproj import Transformer

                    src_epsg = None
                    wkt = info["proj_wkt"]
                    if "EPSG" in wkt:
                        import re

                        m = re.search(r"EPSG\"\s*,\s*([0-9]{3,5})", wkt)
                        if m:
                            src_epsg = int(m.group(1))
                    if src_epsg:
                        transformer = Transformer.from_crs(
                            f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True
                        )
                        fminx, fminy, fmaxx, fmaxy = info["bbox"]
                        ll = transformer.transform(fminx, fminy)
                        ur = transformer.transform(fmaxx, fmaxy)
                        file_bbox_wgs84 = (ll[0], ll[1], ur[0], ur[1])
                        cx_file = (file_bbox_wgs84[0] + file_bbox_wgs84[2]) / 2.0
                        cy_file = (file_bbox_wgs84[1] + file_bbox_wgs84[3]) / 2.0
                        cx_expected = (
                            expected_bbox_wgs84[0] + expected_bbox_wgs84[2]
                        ) / 2.0
                        cy_expected = (
                            expected_bbox_wgs84[1] + expected_bbox_wgs84[3]
                        ) / 2.0
                        import math

                        dist = math.hypot(cx_file - cx_expected, cy_file - cy_expected)
                        if dist <= 0.1:
                            load_path = path
                        else:
                            fixed = self._rewrite_bounds_to_wgs84(
                                path, expected_bbox_wgs84
                            )
                            load_path = fixed or path
                    else:
                        fixed = self._rewrite_bounds_to_wgs84(path, expected_bbox_wgs84)
                        load_path = fixed or path
                except Exception:
                    fixed = self._rewrite_bounds_to_wgs84(path, expected_bbox_wgs84)
                    load_path = fixed or path

            lyr = QgsRasterLayer(
                load_path, os.path.splitext(os.path.basename(load_path))[0], "gdal"
            )
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
                _log(self, f"Loaded raster: {load_path}")
                return True
            else:
                _log(self, f"Failed to load raster: {load_path}", Qgis.Warning)
                return False

        except Exception as e:
            _log(self, f"_try_fix_and_load error: {e}", Qgis.Warning)
            return False

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.outputPathEdit.setText(folder)

    def _reset_form(self):
        self._aoi_bbox = None
        self._aoi_polygon = None
        self._aoi_rect_mapcrs = None
        self._update_aoi_preview("AOI: not set yet")
        if self.commonWidget and hasattr(self.commonWidget, "reset"):
            try:
                self.commonWidget.reset()
            except Exception:
                pass

    def _normalize_bbox_against_canvas(self, bbox_wgs84):
        try:
            if not bbox_wgs84 or len(bbox_wgs84) != 4:
                return bbox_wgs84, "invalid"

            canvas = self.iface.mapCanvas()
            extent_map = canvas.extent()

            lonmin_a, latmin_a, lonmax_a, latmax_a = bbox_wgs84
            center_a_lon = (lonmin_a + lonmax_a) / 2.0
            center_a_lat = (latmin_a + latmax_a) / 2.0

            lonmin_b, latmin_b, lonmax_b, latmax_b = (
                bbox_wgs84[1],
                bbox_wgs84[0],
                bbox_wgs84[3],
                bbox_wgs84[2],
            )
            center_b_lon = (lonmin_b + lonmax_b) / 2.0
            center_b_lat = (latmin_b + latmax_b) / 2.0

            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            dst_crs = canvas.mapSettings().destinationCrs()
            xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

            def to_map_point(lon, lat):
                try:
                    pt = xform.transform(lon, lat)
                    return QgsPointXY(pt.x(), pt.y())
                except Exception:
                    p = xform.transform(lon, lat)
                    return QgsPointXY(p.x(), p.y())

            center_a_map = to_map_point(center_a_lon, center_a_lat)
            center_b_map = to_map_point(center_b_lon, center_b_lat)

            in_a = extent_map.contains(center_a_map)
            in_b = extent_map.contains(center_b_map)

            if in_a and not in_b:
                return bbox_wgs84, "ok"
            if in_b and not in_a:
                corrected = [lonmin_b, latmin_b, lonmax_b, latmax_b]
                return corrected, "swapped"
            return bbox_wgs84, "ambiguous"
        except Exception as e:
            _log(self, f"_normalize_bbox_against_canvas error: {e}", Qgis.Warning)
            return bbox_wgs84, "error"

    def _open_help(self):
        QMessageBox.information(self, "Help", "VirtuGhan Extractor Help coming soon.")

    def _collect_params(self):
        if ExtractorBackend is None:
            raise RuntimeError(
                f"Extractor backend import failed: {EXTRACTOR_IMPORT_ERROR}"
            )
        if not self._aoi_bbox:
            raise RuntimeError("Please set AOI before running.")
        if _bbox_looks_projected(self._aoi_bbox):
            raise RuntimeError(
                f"AOI bbox does not look like EPSG:4326: {self._aoi_bbox}"
            )

        p = self._get_common_params()
        sdt = QDate.fromString(p["start_date"], "yyyy-MM-dd")
        edt = QDate.fromString(p["end_date"], "yyyy-MM-dd")
        if not sdt.isValid() or not edt.isValid():
            raise RuntimeError("Please pick valid start/end dates.")
        if sdt > edt:
            raise RuntimeError("Start date must be before end date.")

        selected_items = self.bandsListWidget.selectedItems()
        bands_list = [i.text().strip() for i in selected_items if i.text().strip()]
        if not bands_list:
            raise RuntimeError("Please select at least one band to extract.")

        zip_out = self.zipOutputCheck.isChecked()
        smart = self.smartFilterCheck.isChecked()

        workers = max(1, int(self.workersSpin.value()))
        out_base = (
            self.outputPathEdit.text() or ""
        ).strip() or QgsProcessingUtils.tempFolder()
        out_dir = os.path.join(out_base, f"virtughan_extractor_{uuid.uuid4().hex[:8]}")

        params = dict(
            bbox=self._aoi_bbox,
            start_date=p["start_date"],
            end_date=p["end_date"],
            cloud_cover=int(p["cloud_cover"]),
            bands_list=bands_list,
            zip_output=zip_out,
            smart_filter=smart,
            workers=workers,
            output_dir=out_dir,
        )

        if hasattr(self, "_aoi_polygon_wgs84") and self._aoi_polygon_wgs84:
            params["polygon_wgs84"] = self._aoi_polygon_wgs84

        try:
            if params.get("bbox") and hasattr(self, "_normalize_bbox_against_canvas"):
                norm_bbox, why = self._normalize_bbox_against_canvas(params["bbox"])
                if why == "swapped":
                    _log(self, f"Normalized bbox (swapped lat/lon) -> {norm_bbox}")
                    params["bbox"] = norm_bbox
                elif why == "ambiguous":
                    _log(
                        self,
                        f"AOI bbox ambiguous vs canvas; using original: {params['bbox']}",
                    )
                elif why == "ok":
                    _log(self, f"AOI bbox OK: {params['bbox']}")
                else:
                    _log(self, f"AOI bbox normalization result: {why}")
        except Exception as e:
            _log(self, f"bbox normalization error: {e}", Qgis.Warning)

        return params

    def _run_clicked(self):
        try:
            params = self._collect_params()
        except Exception as e:
            QMessageBox.warning(self, "VirtuGhan", str(e))
            return
        try:
            norm_bbox, why = self._normalize_bbox_against_canvas(params["bbox"])
            if why == "swapped":
                _log(self, f"Normalized bbox (swapped lat/lon) -> {norm_bbox}")
                params["bbox"] = norm_bbox
            elif why == "ambiguous":
                _log(
                    self,
                    f"AOI bbox ambiguous vs canvas; using original: {params['bbox']}",
                )
            elif why == "error":
                _log(self, "AOI bbox normalization had an error; using original.")
            else:
                _log(self, f"AOI bbox OK: {params['bbox']}")
        except Exception as _e:
            _log(self, f"Failed to normalize bbox: {_e}", Qgis.Warning)

        _log(self, f"Running extractor with bbox: {params.get('bbox')}")
        if params.get("polygon_wgs84"):
            _log(
                self,
                f"Running extractor with polygon_wgs84 (first 6 coords): {params['polygon_wgs84'][:6]}",
            )
        try:
            self._draw_debug_bbox(params["bbox"])
        except Exception:
            pass

        out_dir = params["output_dir"]
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self, "VirtuGhan", f"Cannot create output folder:\n{out_dir}\n\n{e}"
            )
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
                QMessageBox.critical(
                    self,
                    "VirtuGhan",
                    f"Extractor failed:\n{exc}\n\nSee runtime.log for details.",
                )
            else:
                added = 0
                for root, _dirs, files in os.walk(out_dir):
                    for fn in files:
                        if fn.lower().endswith((".tif", ".tiff", ".vrt")):
                            path = os.path.join(root, fn)
                            expected_bbox = getattr(self, "_aoi_bbox", None)
                            ok = self._try_fix_and_load(
                                path, expected_bbox if expected_bbox else None
                            )
                            if ok:
                                added += 1
                            else:
                                _log(
                                    self,
                                    f"Failed to load raster even after fix attempt: {path}",
                                    Qgis.Warning,
                                )
                if added == 0:
                    _log(self, "No raster files found to load.")
                QMessageBox.information(
                    self, "VirtuGhan", f"Extractor finished.\nOutput: {out_dir}"
                )

        self._current_task = _ExtractorTask(
            "VirtuGhan Extractor", params, log_path, on_done=_on_done
        )
        QgsApplication.taskManager().addTask(self._current_task)
