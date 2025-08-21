import os
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtWidgets import QWidget, QMessageBox, QDockWidget
from .tiler_logic import TilerLogic

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), "tiler_form.ui"))

class TilerWidget(QWidget, FORM_CLASS):
    """
    Dockable widget for configuring and loading the VirtuGhan Tiler
    as an XYZ raster layer in QGIS.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.logic = TilerLogic(iface)

        self._init_defaults()
        self._wire_signals()
        self._apply_timeseries_visibility()

    def _init_defaults(self):
        # Dates: last 30 days
        today = QDate.currentDate()
        self.endDateEdit.setDate(today)
        self.startDateEdit.setDate(today.addDays(-30))

        # Cloud %
        self.cloudSpin.setRange(0, 100)
        self.cloudSpin.setValue(30)

        # Bands (engine-style names)
        if self.band1Combo.count() == 0:
            self.band1Combo.addItems(["red", "green", "blue", "nir", "swir1", "swir2"])
        if self.band2Combo.count() == 0:
            self.band2Combo.addItems(["", "red", "green", "blue", "nir", "swir1", "swir2"])

        # Default NDVI using red/nir
        if not self.formulaLine.text():
            self.formulaLine.setText("(band2 - band1) / (band2 + band1)")
        # Defaults matching NDVI
        self.band1Combo.setCurrentText("red")
        self.band2Combo.setCurrentText("nir")

        # Operations for time series aggregation
        self.operationCombo.clear()
        self.operationCombo.addItems(["median", "mean", "min", "max"])

        # Backend base URL (host of your API)
        if not self.backendUrlLine.text():
            self.backendUrlLine.setText("http://127.0.0.1:8000")

        # Layer display name in QGIS Layers panel
        if not self.layerNameLine.text():
            self.layerNameLine.setText("VirtuGhan Tiler")

        # Time series: default OFF (unchecked)
        self.timeseriesCheck.setChecked(False)

    def _wire_signals(self):
        self.addLayerBtn.clicked.connect(self._on_add_layer)
        self.resetBtn.clicked.connect(self._on_reset)
        self.helpBtn.clicked.connect(self._on_help)
        self.timeseriesCheck.toggled.connect(self._apply_timeseries_visibility)

    def _apply_timeseries_visibility(self):
        # Show/hide operation controls based on timeseries toggle
        show = self.timeseriesCheck.isChecked()
        self.labelOp.setVisible(show)
        self.operationCombo.setVisible(show)

    def _on_help(self):
        QMessageBox.information(
            self,
            "VirtuGhan Tiler",
            (
                "Adds a live XYZ layer rendered by your FastAPI Tiler.\n\n"
                "1) Set date range, cloud %, bands, formula.\n"
                "2) Optionally enable 'Time series' and choose an aggregation.\n"
                "3) Provide the backend base URL (e.g., http://127.0.0.1:8000).\n"
                "4) Click 'Add XYZ Layer'.\n\n"
                "Tip: NDVI → band1=red, band2=nir, formula=(band2 - band1)/(band2 + band1)."
            ),
        )

    def _on_reset(self):
        self._init_defaults()
        self._apply_timeseries_visibility()

    def _validate(self):
        backend = self.backendUrlLine.text().strip()
        if not backend:
            raise ValueError("Backend URL cannot be empty.")

        name = self.layerNameLine.text().strip()
        if not name:
            raise ValueError("Layer name cannot be empty.")

        start = self.startDateEdit.date()
        end = self.endDateEdit.date()
        if start > end:
            raise ValueError("Start date must be before or equal to End date.")

        formula = self.formulaLine.text().strip()
        if not formula:
            raise ValueError("Formula cannot be empty.")

        return True

    def _collect_params(self):
        start_date = self.startDateEdit.date().toString("yyyy-MM-dd")
        end_date = self.endDateEdit.date().toString("yyyy-MM-dd")
        cloud_cover = int(self.cloudSpin.value())
        band1 = self.band1Combo.currentText().strip()
        band2 = self.band2Combo.currentText().strip()
        formula = self.formulaLine.text().strip()
        timeseries = self.timeseriesCheck.isChecked()
        operation = self.operationCombo.currentText().strip() if timeseries else None
        return (start_date, end_date, cloud_cover, band1, band2, formula, timeseries, operation)

    def _on_add_layer(self):
        try:
            self._validate()
            backend_url = self.backendUrlLine.text().strip()
            layer_name = self.layerNameLine.text().strip()

            (start_date, end_date, cloud_cover, band1, band2, formula, timeseries, operation) = self._collect_params()

            params = self.logic.default_params(
                start_date=start_date,
                end_date=end_date,
                cloud_cover=cloud_cover,
                band1=band1,
                band2=band2,
                formula=formula,
                timeseries=timeseries,
                operation=operation,
            )

            layer = self.logic.add_xyz_layer(backend_url, layer_name, params)
            QMessageBox.information(
                self,
                "Layer Added",
                f"'{layer_name}' added successfully.\nProvider URI:\n{layer.source()}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class TilerDockWidget(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("VirtuGhan • Tiler", parent)
        self._content = TilerWidget(iface, self)
        self.setWidget(self._content)
