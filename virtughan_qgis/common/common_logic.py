import os, json

from qgis.core import Qgis, QgsMessageLog

def load_bands_meta():
    """
    Try vendored JSON first, else package resource via importlib.resources.
    Returns dict or None.
    """
    # vendored path
    here = os.path.dirname(__file__)
    vendored = os.path.join(os.path.dirname(here), "libs", "virtughan", "data", "sentinel-2-bands.json")
    if os.path.exists(vendored):
        try:
            with open(vendored, "r") as f:
                return json.load(f)
        except Exception:
            pass

    # installed package resource
    try:
        import importlib.resources as resources
        with resources.as_file(resources.files("virtughan").joinpath("data/sentinel-2-bands.json")) as p:
            if p.exists():
                with open(p, "r") as f:
                    return json.load(f)
    except Exception:
        pass

    QgsMessageLog.logMessage("sentinel-2-bands.json not found; falling back to default band list.", "VirtuGhan", Qgis.Warning)
    return None

def default_band_list():
    return ["red","green","blue","nir","nir08","swir16","swir22","rededge1","rededge2","rededge3","visual"]

def populate_band_combos(band1_combo, band2_combo, bands_meta=None):
    bands = list(bands_meta.keys()) if bands_meta else default_band_list()
    band1_combo.clear(); band2_combo.clear()
    band1_combo.addItems(bands)
    band2_combo.addItems([""] + bands)  # allow empty

def check_resolution_warning(bands_meta, band1, band2):
    """
    Return a warning string if GSD differs, else None.
    """
    if not bands_meta or not band1 or not band2 or band1 == band2:
        return None
    g1 = bands_meta.get(band1, {}).get("gsd")
    g2 = bands_meta.get(band2, {}).get("gsd")
    if g1 and g2 and g1 != g2:
        return f"Band resolution mismatch: {band1}={g1}m, {band2}={g2}m."
    return None

def auto_workers():
    try:
        import multiprocessing
        return max(1, multiprocessing.cpu_count() - 1)
    except Exception:
        return 1

def qdate_to_iso(qdate):
    return qdate.toString("yyyy-MM-dd")
