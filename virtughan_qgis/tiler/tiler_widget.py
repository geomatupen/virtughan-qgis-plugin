import os
import sys
import threading
import importlib
import pkgutil
import logging

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QDate
from qgis.PyQt.QtWidgets import QWidget, QMessageBox, QDockWidget
from qgis.core import QgsMessageLog, Qgis, QgsProject

from .tiler_logic import TilerLogic

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), "tiler_form.ui"))


class _InProcessServerManager:
    """
    Run uvicorn INSIDE this QGIS process on a background thread (Windows-safe).
    Workers are forced to 1. If you need multi-workers, run uvicorn externally.
    """
    def __init__(self):
        self._server = None
        self._thread = None
        self._running = False
        self._bound_host = None
        self._bound_port = None

    def is_running(self) -> bool:
        return bool(self._running and self._server and not getattr(self._server, "should_exit", False))

    def start(self, app_path: str, host: str = "127.0.0.1", port: int = 8002, workers: int = 1):
        """
        Start in-process uvicorn. If app_path is empty or invalid, auto-discover any FastAPI app
        under virtughan.*. Logs which app was chosen. Tries subsequent ports if busy.
        """
        if self.is_running():
            return

        from fastapi import FastAPI
        import uvicorn

        def _log(msg: str):
            QgsMessageLog.logMessage(msg, "VirtuGhan", Qgis.Info)

        def _resolve_app(path: str):
            """Try 'module:function' or 'file.py:function'. Returns (app, chosen_path) or (None,None)."""
            if not path or ":" not in path:
                return None, None
            mod_raw, fn_raw = path.split(":", 1)
            mod_raw, fn = mod_raw.strip(), fn_raw.strip()

            # file path support
            if mod_raw.lower().endswith(".py") or ("\\" in mod_raw) or ("/" in mod_raw):
                full = os.path.abspath(os.path.expanduser(mod_raw))
                if not os.path.isfile(full):
                    _log(f"[uvicorn] File not found: {full}")
                    return None, None
                app_dir = os.path.dirname(full)
                module_name = os.path.splitext(os.path.basename(full))[0]
                if app_dir not in sys.path:
                    sys.path.insert(0, app_dir)
            else:
                module_name = mod_raw

            try:
                m = importlib.import_module(module_name)
                app = getattr(m, fn)
                if isinstance(app, FastAPI):
                    return app, f"{module_name}:{fn}"
            except Exception as e:
                _log(f"[uvicorn] Could not import {module_name}:{fn} ({e}).")
            return None, None

        # 1) use the provided App Path first
        app, chosen = _resolve_app(app_path)

        # 2) if blank or wrong, discover a FastAPI app under virtughan.*
        if app is None:
            candidates = []
            try:
                import virtughan  # noqa
            except Exception:
                pass

            from fastapi import FastAPI as _Fast
            for root in ("virtughan",):
                try:
                    pkg = importlib.import_module(root)
                except Exception:
                    continue
                try:
                    for m in pkgutil.walk_packages(pkg.__path__, root + "."):
                        if m.ispkg:
                            continue
                        try:
                            mod = importlib.import_module(m.name)
                            for name, obj in vars(mod).items():
                                if isinstance(obj, _Fast):
                                    candidates.append(f"{m.name}:{name}")
                        except Exception:
                            pass
                except Exception:
                    pass

            if candidates:
                _log("Discovered FastAPI apps:\n  " + "\n  ".join(candidates))
                for cand in candidates:
                    app, chosen = _resolve_app(cand)
                    if app is not None:
                        break

        if app is None:
            raise RuntimeError(
                "Could not locate a FastAPI app to run.\n"
                "• Set App Path to 'virtughan_qgis.tiler.api:app' (recommended),\n"
                "  or 'C:\\path\\to\\api.py:app'.\n"
                "• Or set an installed module path like 'virtughan.<module>:app' if your package provides one."
            )

        # Route uvicorn logs into QGIS Messages; avoid duplicate handlers
        uv_logger = logging.getLogger("uvicorn")
        uv_logger.setLevel(logging.INFO)

        class _QgisHandler(logging.Handler):
            def emit(self, record):
                try:
                    QgsMessageLog.logMessage(f"[uvicorn] {self.format(record)}", "VirtuGhan", Qgis.Info)
                except Exception:
                    pass

        for h in list(uv_logger.handlers):
            if isinstance(h, _QgisHandler):
                uv_logger.removeHandler(h)
        uv_logger.addHandler(_QgisHandler())

        # Build server with no default log_config (prevents 'formatter default' error)
        def _make_server(bind_port: int):
            cfg = uvicorn.Config(
                app=app,
                host=host,
                port=int(bind_port),
                log_level="info",
                log_config=None,   # important: do not install uvicorn's dictConfig
                access_log=False,  # optional: reduce noise
            )
            return uvicorn.Server(cfg)

        # Try ports: requested, then next free up to +20
        last_err = None
        for attempt in range(21):
            try_port = int(port) + attempt
            try:
                self._server = _make_server(try_port)

                def _run():
                    self._running = True
                    try:
                        _log(f"In-process uvicorn: using {chosen} on http://{host}:{try_port}")
                        self._server.run()
                    finally:
                        self._running = False

                self._thread = threading.Thread(target=_run, daemon=True)
                self._thread.start()
                # record bound host/port for caller
                self._bound_host = host
                self._bound_port = try_port
                return
            except OSError as oe:
                last_err = oe
                continue
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Failed to start local server on {host}:{port} (and subsequent ports). Last error: {last_err}")

    def stop(self):
        if self._server is not None:
            try:
                self._server.should_exit = True
            except Exception:
                pass
        self._server = None
        self._thread = None
        self._running = False
        self._bound_host = None
        self._bound_port = None


class TilerWidget(QWidget, FORM_CLASS):
    """Dockable widget for configuring and loading the VirtuGhan Tiler."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.logic = TilerLogic(iface)
        self.server = _InProcessServerManager()

        self._init_defaults()
        self._wire_signals()
        self._apply_timeseries_visibility()
        self._apply_localserver_visibility()
        QgsProject.instance().layersRemoved.connect(self._on_layers_removed)

    # ---- helpers ----
    def _log(self, msg: str):
        QgsMessageLog.logMessage(msg, "VirtuGhan", Qgis.Info)

    def _init_defaults(self):
        # Dates: last 30 days
        today = QDate.currentDate()
        self.endDateEdit.setDate(today)
        self.startDateEdit.setDate(today.addDays(-30))

        # Cloud %
        self.cloudSpin.setRange(0, 100)
        self.cloudSpin.setValue(30)

        # Bands (include 'visual' but default to NDVI config)
        if self.band1Combo.count() == 0:
            self.band1Combo.addItems(["visual", "red", "green", "blue", "nir", "swir1", "swir2"])
        if self.band2Combo.count() == 0:
            self.band2Combo.addItems(["", "red", "green", "blue", "nir", "swir1", "swir2"])

        # Default to NDVI: band1=red, band2=nir, formula = (band2 - band1)/(band2 + band1)
        self.band1Combo.setCurrentText("red")
        self.band2Combo.setCurrentText("nir")
        if not self.formulaLine.text():
            self.formulaLine.setText("(band2 - band1) / (band2 + band1)")

        # Time series OFF by default
        self.timeseriesCheck.setChecked(False)
        self.operationCombo.clear()
        self.operationCombo.addItems(["median", "mean", "min", "max"])

        # Backend URL (local, default port now 8002)
        if not self.backendUrlLine.text():
            self.backendUrlLine.setText("http://127.0.0.1:8002")

        # Layer name
        if not self.layerNameLine.text():
            self.layerNameLine.setText("VirtuGhan Tiler")

        # Local server defaults
        self.runLocalCheck.setChecked(True)
        # Pre-fill the exact module path to your embedded API (inside this plugin)
        self.appPathLine.setText("virtughan_qgis.tiler.api:app")

        if not self.hostLine.text():
            self.hostLine.setText("127.0.0.1")
        if self.portSpin.value() == 0:
            self.portSpin.setRange(1, 65535)
            self.portSpin.setValue(8002)  # default 8002 as requested
        if self.workersSpin.value() == 0:
            self.workersSpin.setRange(1, 64)
            self.workersSpin.setValue(1)

    def _wire_signals(self):
        self.addLayerBtn.clicked.connect(self._on_add_layer)
        self.resetBtn.clicked.connect(self._on_reset)
        self.helpBtn.clicked.connect(self._on_help)
        self.timeseriesCheck.toggled.connect(self._apply_timeseries_visibility)
        self.runLocalCheck.toggled.connect(self._apply_localserver_visibility)
        self.startServerBtn.clicked.connect(self._on_start_server)
        self.stopServerBtn.clicked.connect(self._on_stop_server)

    def _apply_timeseries_visibility(self):
        show = self.timeseriesCheck.isChecked()
        self.labelOp.setVisible(show)
        self.operationCombo.setVisible(show)

    def _apply_localserver_visibility(self):
        enabled = self.runLocalCheck.isChecked()
        running = False
        try:
            running = self.server.is_running()
        except Exception:
            running = False
        self.startServerBtn.setEnabled(enabled and not running)
        self.stopServerBtn.setEnabled(enabled and running)
        if enabled:
            host = (self.hostLine.text().strip() or "127.0.0.1")
            # prefer bound port if already running (auto-bumped)
            bound_port = getattr(self.server, "_bound_port", None)
            port = bound_port if bound_port else int(self.portSpin.value())
            self.backendUrlLine.setText(f"http://{host}:{port}")

    # ---- UI actions ----
    def _on_help(self):
        QMessageBox.information(
            self,
            "VirtuGhan Tiler",
            "Adds an XYZ layer rendered by your local FastAPI server.\n\n"
            "• App Path defaults to virtughan_qgis.tiler.api:app (embedded).\n"
            "• Set NDVI defaults (red/nir and formula) or choose visual/index.\n"
            "• Optional: enable Time series and choose an aggregation.\n"
            "• Workers are forced to 1 in-process.",
        )

    def _on_reset(self):
        self._init_defaults()
        self._apply_timeseries_visibility()
        self._apply_localserver_visibility()

    def _validate(self):
        if not self.backendUrlLine.text().strip():
            raise ValueError("Backend URL cannot be empty.")
        if not self.layerNameLine.text().strip():
            raise ValueError("Layer name cannot be empty.")
        if self.startDateEdit.date() > self.endDateEdit.date():
            raise ValueError("Start date must be before or equal to End date.")
        if not self.formulaLine.text().strip():
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

    def _on_start_server(self):
        try:
            app_path = self.appPathLine.text().strip()  # e.g., virtughan_qgis.tiler.api:app
            host = self.hostLine.text().strip() or "127.0.0.1"
            requested_port = int(self.portSpin.value() or 8002)

            if not self.server.is_running():
                self.server.start(app_path=app_path, host=host, port=requested_port, workers=1)
                # If server auto-bumped port, reflect it in UI and backend URL
                bound_port = getattr(self.server, "_bound_port", requested_port)
                if bound_port != requested_port:
                    self.portSpin.setValue(bound_port)
                self.backendUrlLine.setText(f"http://{host}:{bound_port}")
                self._log(f"Local uvicorn (in-process) listening at http://{host}:{bound_port}")
                self._apply_localserver_visibility()
            else:
                self._log("Local server already running.")
        except Exception as e:
            QMessageBox.critical(self, "Start Server Error", str(e))

    def _on_stop_server(self):
        try:
            self.server.stop()
            self._log("Local server stopped.")
            self._apply_localserver_visibility()
        except Exception as e:
            QMessageBox.critical(self, "Stop Server Error", str(e))

    def _on_add_layer(self):
        try:
            self._validate()
            if self.runLocalCheck.isChecked() and not self.server.is_running():
                self._on_start_server()
                if not self.server.is_running():
                    raise RuntimeError("Local server did not start. Check App Path / port.")
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
            self._log(f"Added layer '{layer_name}' with source: {layer.source()}")
            QMessageBox.information(self, "Layer Added", f"'{layer_name}' added successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_layers_removed(self, layer_ids):
        try:
            if not self.runLocalCheck.isChecked():
                return
            still_has_tiler = any(
                "/tile/{z}/{x}/{y}" in getattr(lyr, "source", lambda: "")()
                for lyr in QgsProject.instance().mapLayers().values()
            )
            if not still_has_tiler and self.server.is_running():
                self.server.stop()
                self._log("Local server stopped (no more Tiler layers).")
                self._apply_localserver_visibility()
        except Exception:
            pass


class TilerDockWidget(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("VirtuGhan • Tiler", parent)
        self._content = TilerWidget(iface, self)
        self.setWidget(self._content)
