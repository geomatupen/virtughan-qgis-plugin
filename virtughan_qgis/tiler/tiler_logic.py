from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QUrl, QUrlQuery

class TilerLogic:
    """
    Create/register an XYZ tile layer that proxies to your FastAPI tiler.
    """

    # Your live endpoint does NOT have .png in the path
    TILER_PATH = "/tile/{z}/{x}/{y}"

    def __init__(self, iface):
        self.iface = iface

    def _build_query(self, params: dict) -> str:
        """
        Build a query string from params, omitting None and preserving booleans.
        """
        q = QUrlQuery()
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, bool):
                q.addQueryItem(k, "true" if v else "false")
            else:
                q.addQueryItem(k, str(v))
        return q.query(QUrl.FullyEncoded)

    def build_xyz_uri(self, backend_url: str, name: str, params: dict) -> str:
        backend_url = backend_url.rstrip("/")
        base = f"{backend_url}{self.TILER_PATH}"
        qs = self._build_query(params)

        # Only append ? if there are any params
        url_template = f"{base}?{qs}" if qs else base
        return f"type=xyz&url={url_template}"

    def add_xyz_layer(self, backend_url: str, name: str, params: dict):
        uri = self.build_xyz_uri(backend_url, name, params)
        layer = QgsRasterLayer(uri, name, "wms")  # XYZ via 'wms' provider
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
        operation: str | None = None,
    ) -> dict:
        """
        Build params expected by your API. When timeseries is False,
        omit timeseries/operation from the URL.
        """
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
