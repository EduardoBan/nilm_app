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

            result = nilm.analyze_dataset(
                dataset_id=dataset_id,
                n_clusters=n_clusters,
                algorithm=algorithm,
                current_threshold=current_threshold,
                power_threshold=power_threshold
            )
            self.write_json({"status": "success", "data": result})
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
        (r"/api/analyze", AnalyzeHandler),
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
