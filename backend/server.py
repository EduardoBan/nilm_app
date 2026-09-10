import os
import sys
import json
import numpy as np
import tornado.ioloop
import tornado.web
import tornado.escape
from typing import Any

# Configure stdout utf-8 for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from backend.data_manager import DataManager
from backend.nilm_engine import NILMEngine

dm = DataManager()
nilm = NILMEngine(dm)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with, content-type")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.set_header("Content-Type", "application/json; charset=UTF-8")

    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    def write_json(self, data: Any):
        payload = json.dumps(data, cls=NumpyEncoder, ensure_ascii=False, indent=2)
        self.write(payload)

class DatasetsHandler(BaseHandler):
    def get(self):
        try:
            datasets = dm.list_datasets()
            self.write_json({"status": "success", "data": datasets})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class SummaryHandler(BaseHandler):
    def get(self):
        try:
            dataset_id = self.get_argument("dataset_id", "coop_gouge_v2_10_abril")
            stats = dm.get_summary_stats(dataset_id)
            self.write_json({"status": "success", "data": stats})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class TimeseriesHandler(BaseHandler):
    def get(self):
        try:
            dataset_id = self.get_argument("dataset_id", "coop_gouge_v2_10_abril")
            max_points = int(self.get_argument("max_points", "1200"))
            ts_data = dm.get_decimated_timeseries(dataset_id, max_points)
            self.write_json({"status": "success", "data": ts_data})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class HarmonicsHandler(BaseHandler):
    def get(self):
        try:
            dataset_id = self.get_argument("dataset_id", "coop_gouge_v2_10_abril")
            harmonics = dm.get_harmonics_summary(dataset_id)
            self.write_json({"status": "success", "data": harmonics})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class UploadHandler(BaseHandler):
    """Accepts a measurement file (.xlsx/.xls/.csv) chosen by the user and makes
    it available for analysis through the standard dataset endpoints."""

    ALLOWED_EXT = {".xlsx", ".xls", ".csv"}

    def post(self):
        try:
            file_field = self.request.files.get("file")
            if not file_field:
                self.set_status(400)
                self.write_json({"status": "error", "message": "No se recibió ningún archivo (campo 'file')."})
                return

            fileinfo = file_field[0]
            filename = fileinfo.get("filename", "") or "medicion.xlsx"
            content = fileinfo.get("body", b"")
            ext = os.path.splitext(filename)[1].lower()

            if ext not in self.ALLOWED_EXT:
                self.set_status(400)
                self.write_json({"status": "error", "message": f"Extensión no soportada '{ext}'. Usa .xlsx, .xls o .csv."})
                return

            dest = dm.save_upload(filename, content)
            dataset_id = dm.get_slug(os.path.basename(dest))
            info = {
                "id": dataset_id,
                "filename": os.path.basename(dest),
                "label": f"Medición {os.path.basename(dest)}",
                "cached": False,
                "size_mb": round(os.path.getsize(dest) / (1024 * 1024), 2)
            }
            self.write_json({"status": "success", "data": info})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class LabelsHandler(BaseHandler):
    """Manual appliance renaming (Ground Truth). Labels are persisted per
    dataset + cluster id and override the automatic heuristic names."""

    def get(self):
        try:
            dataset_id = self.get_argument("dataset_id", "")
            self.write_json({"status": "success", "data": {"labels": dm.get_labels(dataset_id)}})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

    def post(self):
        try:
            req = tornado.escape.json_decode(self.request.body) if self.request.body else {}
            dataset_id = str(req.get("dataset_id", "")).strip()
            cluster_id = int(req.get("cluster_id"))
            name = str(req.get("name", ""))
            if not dataset_id:
                raise ValueError("dataset_id es requerido")
            labels = dm.set_label(dataset_id, cluster_id, name)
            self.write_json({"status": "success", "data": {"labels": labels}})
        except Exception as e:
            self.set_status(400)
            self.write_json({"status": "error", "message": str(e)})

    def delete(self):
        try:
            dataset_id = self.get_argument("dataset_id", "")
            if not dataset_id and self.request.body:
                try:
                    req = tornado.escape.json_decode(self.request.body)
                    dataset_id = str(req.get("dataset_id", "")).strip()
                except Exception:
                    pass
            if not dataset_id:
                raise ValueError("dataset_id es requerido")
            labels = dm.clear_labels(dataset_id)
            self.write_json({"status": "success", "data": {"labels": labels, "message": "Etiquetas restablecidas a valores automáticos"}})
        except Exception as e:
            self.set_status(400)
            self.write_json({"status": "error", "message": str(e)})

class AnalyzeHandler(BaseHandler):
    def get(self):
        self.post()

    def post(self):
        try:
            req_data = {}
            if self.request.body:
                try:
                    req_data = tornado.escape.json_decode(self.request.body)
                except Exception:
                    req_data = {}

            dataset_id = req_data.get("dataset_id") or self.get_argument("dataset_id", "coop_gouge_v2_10_abril")
            n_clusters = int(req_data.get("n_clusters") or self.get_argument("n_clusters", "4"))
            algorithm = str(req_data.get("algorithm") or self.get_argument("algorithm", "kmeans"))
            current_threshold = float(req_data.get("current_threshold") or self.get_argument("current_threshold", "2.0"))
            power_threshold = float(req_data.get("power_threshold") or self.get_argument("power_threshold", "1.0"))

            use_fhmm_raw = req_data.get("use_fhmm")
            if use_fhmm_raw is None:
                use_fhmm = self.get_argument("use_fhmm", "false").lower() in ("1", "true", "yes", "on")
            else:
                use_fhmm = bool(use_fhmm_raw)
            max_states = int(req_data.get("max_states") or self.get_argument("max_states", "3"))

            # Manual Ground-Truth labels persisted for this dataset (or passed in request)
            labels = req_data.get("labels")
            if not labels or not isinstance(labels, dict):
                labels = dm.get_labels(dataset_id)

            result = nilm.analyze_dataset(
                dataset_id=dataset_id,
                n_clusters=n_clusters,
                algorithm=algorithm,
                current_threshold=current_threshold,
                power_threshold=power_threshold,
                use_fhmm=use_fhmm,
                max_states=max_states,
                labels=labels
            )
            self.write_json({"status": "success", "data": result})
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

class ReportHandler(BaseHandler):
    def get(self):
        try:
            dataset_id = self.get_argument("dataset_id", "coop_gouge_v2_10_abril")
            n_clusters = int(self.get_argument("n_clusters", "4"))
            algorithm = self.get_argument("algorithm", "kmeans")

            reports_dir = os.path.join(BASE_DIR, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            pdf_path = os.path.join(reports_dir, f"Informe_NILM_{dataset_id}.pdf")
            default_pdf = os.path.join(BASE_DIR, "Informe_NILM_Inti.pdf")

            from scripts.generate_report import generate_report
            labels = dm.get_labels(dataset_id)
            generate_report(
                dataset_id=dataset_id,
                n_clusters=n_clusters,
                algorithm=algorithm,
                output_path=Path(pdf_path),
                labels=labels
            )

            target_path = pdf_path if os.path.exists(pdf_path) else default_pdf
            if not os.path.exists(target_path):
                self.set_status(404)
                self.write_json({"status": "error", "message": "Informe PDF no encontrado."})
                return
            self.set_header("Content-Type", "application/pdf")
            self.set_header("Content-Disposition", f'inline; filename="Informe_NILM_{dataset_id}.pdf"')
            with open(target_path, "rb") as f:
                self.write(f.read())
        except Exception as e:
            self.set_status(500)
            self.write_json({"status": "error", "message": str(e)})

def make_app():
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    return tornado.web.Application([
        (r"/api/datasets", DatasetsHandler),
        (r"/api/summary", SummaryHandler),
        (r"/api/timeseries", TimeseriesHandler),
        (r"/api/harmonics", HarmonicsHandler),
        (r"/api/upload", UploadHandler),
        (r"/api/analyze", AnalyzeHandler),
        (r"/api/labels", LabelsHandler),
        (r"/api/report", ReportHandler),
        (r"/(.*)", tornado.web.StaticFileHandler, {
            "path": frontend_dir,
            "default_filename": "index.html"
        }),
    ], debug=True)

if __name__ == "__main__":
    port = 8000
    app = make_app()
    app.listen(port)
    print("===========================================================")
    print(f"  [+] Servidor NILM en Ejecucion: http://localhost:{port}")
    print(f"  [+] Cliente Frontend (TypeScript): http://localhost:{port}")
    print(f"  [+] Datos: C:\\Users\\local\\Documents\\IA\\Energia\\Data")
    print("===========================================================")
    tornado.ioloop.IOLoop.current().start()
