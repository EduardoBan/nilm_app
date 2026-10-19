# Instalador Windows 11 — NILM Energy Analytics Platform

## Contenido

| Archivo | Descripción |
|---------|-------------|
| `install_win11.cmd` | Instalador principal (batch para Windows 10/11) |
| `README.md` | Este archivo |

## Requisitos previos

- **Windows 10 o Windows 11** (64 bits)
- **Python 3.10 o superior** instalado y en el PATH del sistema
- Conexión a internet para descargar dependencias (primera vez)

## Instalación

1. Ejecutar `install_win11.cmd` como usuario normal (no requiere administrador).
2. El instalador hará lo siguiente:
   - Verifica Python 3.10+
   - Crea el directorio `%LOCALAPPDATA%\Programs\NILM_Energy_Platform`
   - Copia backend, frontend y archivos raíz
   - Crea entorno virtual (`.venv`) e instala dependencias de `requirements.txt`
   - Crea directorios de datos (`Data`, `cache`, `reports`)
   - Crea accesos directos en **Escritorio** y **Menú Inicio**
   - Crea un desinstalador (`uninstall.cmd`)

## Uso

- Haga doble clic en **"NILM Energy Platform"** (Escritorio o Menú Inicio).
- La aplicación se abre en el navegador predeterminado en `http://localhost:5000`.
- Para detener: cierre la ventana de la consola (Ctrl+C).

## Desinstalación

Ejecute `%LOCALAPPDATA%\Programs\NILM_Energy_Platform\uninstall.cmd` o elimine manualmente la carpeta de instalación.

## Estructura instalada

```
%LOCALAPPDATA%\Programs\NILM_Energy_Platform\
├── NILM_Platform.cmd      # Lanzador de la aplicacion
├── uninstall.cmd          # Desinstalador
├── server.py              # Servidor backend
├── requirements.txt       # Dependencias Python
├── backend/               # Motor NILM y gestor de datos
├── frontend/              # Interfaz web (HTML, CSS, JS)
├── .venv/                 # Entorno virtual Python
├── Data/                  # Datos cargados por el usuario
├── cache/                 # Cache de datasets
└── reports/               # Informes generados
```

## Solución de problemas

- **Python no encontrado**: Instale Python 3.10+ desde https://python.org y asegúrese de marcar "Add Python to PATH" durante la instalación.
- **Error de dependencias**: Ejecute el instalador nuevamente o instale manualmente: `pip install -r requirements.txt`
- **Puerto 5000 ocupado**: Otra aplicación usa ese puerto; cierrela o cambie el puerto en `server.py`.