from typing import Optional
from urllib.parse import urlencode, quote  # NOTE: using quote (not quote_plus)

from qgis.core import QgsProject, QgsRasterLayer, QgsMessageLog, Qgis


class TilerLogic:
    """Create/register an XYZ tile layer that proxies to your FastAPI tiler."""
    TILER_PATH = "/tile/{z}/{x}/{y}"  # no .png suffix

    def __init__(self, iface):
        self.iface = iface

    def _build_query(self, params: dict) -> str:
        from urllib.parse import urlencode, quote
        clean = {k: v for k, v in params.items() if v is not None and str(v) != ""}
        # spaces -> %20; '+' must be %2B; allow (),*,/,_ in formulas
        return urlencode(clean, doseq=True, quote_via=quote, safe="()*/_-")


    def build_xyz_uri(self, backend_url: str, name: str, params: dict) -> str:
        backend_url = backend_url.rstrip("/")
        base = f"{backend_url}{self.TILER_PATH}"
        qs = self._build_query(params)
        url_template = f"{base}?{qs}" if qs else base

        # IMPORTANT:
        # Do NOT encode the '?'. Only escape '&' so QGIS doesn't treat them
        # as provider-level options. Leave '?' and '=' as-is.
        url_value = url_template.replace("&", "%26")

        # Match VirtuGhan server zoom limits
        provider_uri = f"type=xyz&zmin=10&zmax=23&url={url_value}"
        return provider_uri


    def add_xyz_layer(self, backend_url: str, name: str, params: dict):
        uri = self.build_xyz_uri(backend_url, name, params)
        QgsMessageLog.logMessage(f"[VirtuGhan Tiler] URI: {uri}", "VirtuGhan", Qgis.Info)
        layer = QgsRasterLayer(uri, name, "wms")  # QGIS uses 'wms' provider for XYZ templates
        if not layer.isValid():
            raise RuntimeError("Failed to create XYZ layer. Check URL/params.")
        QgsProject.instance().addMapLayer(layer)
        return layer

    @staticmethod
    def default_params(
        start_date: str,
        end_date: str,
        cloud_cover: int,
        band1: str,
        band2: str,
        formula: str,
        timeseries: bool = False,
        operation: Optional[str] = None,
    ) -> dict:
        base = {
            "start_date": start_date,
            "end_date": end_date,
            "cloud_cover": cloud_cover,
            "band1": band1,
            "band2": band2 or "",
            "formula": formula,
        }
        if timeseries:
            base["timeseries"] = True
            base["operation"] = operation or "median"
        return base
