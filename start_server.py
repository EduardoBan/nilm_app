"""
NILM (Non-Intrusive Load Monitoring) Energy Analysis and Disaggregation Platform
Runs the Python Tornado backend and serves the TypeScript frontend.
"""
import os
import sys
import webbrowser
import tornado.ioloop

# El runtime portable usa python*._pth y no hereda PYTHONPATH. La raíz de
# la aplicación debe estar explícitamente en sys.path para encontrar backend.
APP_HOME = os.environ.get("NILM_APP_HOME") or os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NILM_APP_HOME", APP_HOME)
if APP_HOME not in sys.path:
    sys.path.insert(0, APP_HOME)
if getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(APP_HOME, "app"))

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from backend.server import make_app

PORT = int(os.environ.get("NILM_PORT", "8000"))

def main():
    app = make_app()
    app.listen(PORT)
    url = f"http://localhost:{PORT}"
    
    print("=" * 65)
    print("  [+] NILM ENERGY ANALYTICS PLATFORM")
    print("  [+] Servidor Python & Cliente TypeScript Activo")
    print(f"  [+] URL: {url}")
    print("  [+] Carpeta de Datos: C:\\Users\\local\\Documents\\IA\\Energia\\Data")
    print("=" * 65)
    print("Presiona Ctrl+C para detener el servidor.\n")
    
    try:
        webbrowser.open(url)
    except Exception:
        pass

    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
