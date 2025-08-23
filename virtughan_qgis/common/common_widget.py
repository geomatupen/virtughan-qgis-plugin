import os
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtCore import QDate
from qgis.core import Qgis, QgsMessageLog
import zipfile

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

        
        self.startDate.setDate(QDate.currentDate().addMonths(-1))
        self.endDate.setDate(QDate.currentDate())
        self.cloudSpin.setRange(0, 100)
        self.cloudSpin.setValue(80)
        self.formulaEdit.setText("(band2-band1)/(band2+band1)")

        populate_band_combos(self.band1Combo, self.band2Combo, self._bands_meta)

        
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


def extract_zipfiles(out_dir: str, logger=None, delete_archives: bool = False) -> list[str]:
    """
    Find and extract all .zip files under `out_dir` into sibling folders named
    after the zip (without extension). Returns a list of destination folders.

    - logger: optional callable (msg, level) -> None; if provided, called for logs
    - delete_archives: if True, remove the .zip after successful extraction
    """
    extracted_dirs: list[str] = []

    def _log(msg, level=Qgis.Info):
        if logger:
            try:
                logger(msg, level)
            except Exception:
                pass

    try:
        for root, _dirs, files in os.walk(out_dir):
            for fn in files:
                if not fn.lower().endswith(".zip"):
                    continue
                zpath = os.path.join(root, fn)
                dest = os.path.join(root, os.path.splitext(fn)[0])
                os.makedirs(dest, exist_ok=True)
                try:
                    with zipfile.ZipFile(zpath) as zf:
                        # Zip-slip protection
                        dest_abs = os.path.abspath(dest)
                        for zi in zf.infolist():
                            target = os.path.abspath(os.path.join(dest_abs, zi.filename))
                            if not (target == dest_abs or target.startswith(dest_abs + os.sep)):
                                raise RuntimeError(f"Unsafe member path in zip: {zi.filename}")
                        zf.extractall(dest_abs)
                    extracted_dirs.append(dest)
                    _log(f"Extracted zip: {zpath} -> {dest}")
                    if delete_archives:
                        try:
                            os.remove(zpath)
                            _log(f"Deleted archive: {zpath}")
                        except Exception as e:
                            _log(f"Could not delete archive {zpath}: {e}", Qgis.Warning)
                except Exception as e:
                    _log(f"Failed to extract {zpath}: {e}", Qgis.Warning)
    except Exception as e:
        _log(f"Zip extraction step failed: {e}", Qgis.Warning)

    return extracted_dirs
