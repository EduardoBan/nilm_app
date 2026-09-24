"""Verificacion temporal: sirve el frontend y comprueba HTML/bundle/cabeceras."""
import os
import sys
import threading
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import tornado.ioloop  # noqa: E402
from backend.server import make_app  # noqa: E402

PORT = 8123


def main():
    app = make_app()
    app.listen(PORT)
    loop = tornado.ioloop.IOLoop.current()
    t = threading.Thread(target=loop.start, daemon=True)
    t.start()
    time.sleep(2.0)

    ok = True

    r = urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=10)
    html = r.read().decode("utf-8")
    has_new = "fix3d-20260918-benchmark1" in html
    has_btn = 'id="btn-run-benchmark"' in html
    print(f"HTML status={r.status} new_version={has_new} benchmark_btn={has_btn}")
    ok &= has_new and has_btn

    r2 = urllib.request.urlopen(
        f"http://localhost:{PORT}/dist/bundle.js?v=fix3d-20260918-benchmark1", timeout=30)
    bundle = r2.read().decode("utf-8")
    has_rb = "runBenchmark" in bundle
    cache = r2.headers.get("Cache-Control", "")
    print(f"BUNDLE status={r2.status} bytes={len(bundle)} has_runBenchmark={has_rb} "
          f"cache_control='{cache}'")
    ok &= has_rb and "no-cache" in cache

    print("RESULT:", "OK" if ok else "FALLO")
    loop.add_callback(loop.stop)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
