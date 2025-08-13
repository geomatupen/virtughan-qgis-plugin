import os
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import QDate
from qgis.core import Qgis, QgsMessageLog

from .common_logic import (
    load_bands_meta, populate_band_combos, check_resolution_warning,
    auto_workers, qdate_to_iso
)

FORM_PATH = os.path.join(os.path.dirname(__file__), "common_form.ui")

class CommonParamsWidget(QtWidgets.QWidget):
    """
    Reusable panel: startDate, endDate, cloudSpin, band1Combo, band2Combo, formulaEdit.
    API:
      - get_params() -> dict
      - set_defaults(...)
      - warn_resolution_if_needed(callback)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = uic.loadUi(FORM_PATH, self)
        self._bands_meta = load_bands_meta()

        # defaults
        self.startDate.setDate(QDate.currentDate().addMonths(-1))
        self.endDate.setDate(QDate.currentDate())
        self.cloudSpin.setRange(0, 100)
        self.cloudSpin.setValue(30)
        self.formulaEdit.setText("(band2-band1)/(band2+band1)")

        populate_band_combos(self.band1Combo, self.band2Combo, self._bands_meta)

        # resolution warnings on change
        self.band1Combo.currentTextChanged.connect(self._on_band_change)
        self.band2Combo.currentTextChanged.connect(self._on_band_change)

        self._warn_callback = None

    def _on_band_change(self, *_):
        if not self._warn_callback:
            return
        b1 = self.band1Combo.currentText().strip()
        b2 = self.band2Combo.currentText().strip()
        msg = check_resolution_warning(self._bands_meta, b1, b2)
        if msg:
            try:
                self._warn_callback(msg)
            except Exception:
                QgsMessageLog.logMessage(msg, "VirtuGhan", Qgis.Warning)

    def warn_resolution_if_needed(self, callback):
        """Provide a function(str) to be called when we detect a GSD mismatch."""
        self._warn_callback = callback

    def get_params(self):
        return {
            "start_date": qdate_to_iso(self.startDate.date()),
            "end_date": qdate_to_iso(self.endDate.date()),
            "cloud_cover": int(self.cloudSpin.value()),
            "band1": self.band1Combo.currentText().strip(),
            "band2": (self.band2Combo.currentText().strip() or None),
            "formula": self.formulaEdit.text().strip(),
        }

    def set_defaults(self, *, start_date=None, end_date=None, cloud=None, band1=None, band2=None, formula=None):
        if start_date: self.startDate.setDate(start_date)
        if end_date: self.endDate.setDate(end_date)
        if cloud is not None: self.cloudSpin.setValue(int(cloud))
        if band1: self.band1Combo.setCurrentText(band1)
        if band2 is not None: self.band2Combo.setCurrentText(band2)
        if formula: self.formulaEdit.setText(formula)
