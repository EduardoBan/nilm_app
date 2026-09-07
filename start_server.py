"""
Launcher script for NILM Client-Server Application
Runs the Python Tornado backend and serves the TypeScript frontend.
"""
import os
import sys
import webbrowser
import tornado.ioloop

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from backend.server import make_app

PORT = 8000

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
