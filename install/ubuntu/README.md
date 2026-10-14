# Instalacion en Ubuntu Server 24.04

Instalador de la **Plataforma NILM Energy Analytics** para un servidor Ubuntu
24.04 (tambien compatible con Debian 12). Despliega la aplicacion en
`/opt/nilm`, crea un entorno virtual Python aislado y la registra como un
**servicio systemd** que arranca solo y se reinicia si falla.

## Contenido de esta carpeta

| Archivo                     | Descripcion                                             |
|-----------------------------|---------------------------------------------------------|
| `install.sh`                | Instalador principal (idempotente).                    |
| `uninstall.sh`              | Desinstalador.                                          |
| `nilm.service`              | Unidad systemd del servicio.                           |
| `requirements-server.txt`   | Dependencias Python (incluye `matplotlib`, faltante).   |
| `nginx-nilm.conf`           | Reverse proxy opcional (puerto 80).                    |

## Requisitos del servidor

- Ubuntu Server 24.04 (o Debian 12).
- Acceso `sudo` (el instalador debe ejecutarse como root).
- Salida a Internet (para `apt` y `pip`).
- Al menos **2 GB de RAM** y **5 GB de disco** libres.
- El puerto **8000** libre (o el que elijas con `--port`).

## Instalacion rapida

1. **Copia el proyecto al servidor** (por ejemplo con `scp`, `rsync` o `git`):

   ```bash
   # Opcion A: clonar el repo
   git clone https://github.com/EduardoBan/nilm_app.git
   cd nilm_app/install/ubuntu

   # Opcion B: copiar tu carpeta local con scp (desde tu PC)
   scp -r nilm_app/install/ubuntu usuario@IP_DEL_SERVIDOR:~/
   cd ~/ubuntu
   ```

   > Importante: el instalador busca la app **3 niveles por encima** de
   > `install/ubuntu/`. Si copias solo esta carpeta, copiala dentro del repo
   > completo, o ajusta `REPO_ROOT` al inicio de `install.sh`.

2. **Ejecuta el instalador:**

   ```bash
   sudo bash install.sh
   ```

3. **Accede** a la URL que muestra el resumen final, por ejemplo:

   ```
   http://192.168.1.50:8000/
   ```

## Opciones del instalador

```bash
sudo bash install.sh                 # Instalacion estandar (puerto 8000)
sudo bash install.sh --port 8080     # Usar otro puerto
sudo bash install.sh --with-nginx    # Instalar y configurar Nginx (puerto 80)
sudo bash install.sh --no-start      # Instalar pero no arrancar el servicio
```

## Gestion del servicio

```bash
sudo systemctl status nilm      # Ver estado
sudo systemctl start nilm       # Arrancar
sudo systemctl stop nilm        # Detener
sudo systemctl restart nilm     # Reiniciar (tras subir datos nuevos)
sudo systemctl enable nilm      # Arrancar con el sistema (ya lo hace el instalador)
journalctl -u nilm -f           # Ver logs en vivo
```

## Subir datos de medicion

La aplicacion lee los archivos `.xlsx`, `.xls` o `.csv` de la carpeta de datos:

```bash
# Copia tus archivos al servidor (ajusta la ruta de origen):
sudo cp /ruta/local/*.xlsx /opt/nilm/Data/

# Ajusta permisos para el usuario del servicio y refresca:
sudo chown -R nilm:nilm /opt/nilm/Data
sudo systemctl restart nilm
```

Los archivos apareceran en el desplegable de datasets de la interfaz web.
Tambien puedes subirlos desde la propia web con el boton de subida.

## Que se instala y donde

| Ruta                          | Contenido                                   |
|-------------------------------|---------------------------------------------|
| `/opt/nilm/`                  | Codigo de la aplicacion.                    |
| `/opt/nilm/venv/`             | Entorno virtual Python.                     |
| `/opt/nilm/Data/`             | Datos de medicion (.xlsx/.csv).            |
| `/opt/nilm/cache/`            | Cache interna de datasets.                  |
| `/opt/nilm/reports/`          | Informes PDF generados.                     |
| `/etc/systemd/system/nilm.service` | Unidad del servicio.                 |

## Notas y solucion de problemas

- **Puerto ocupado:** usa `--port` para cambiarlo, o libera el 8000.
- **No arranca:** revisa `journalctl -u nilm -n 50`.
- **Sin nilmtk:** el instalador lo instala de forma tolerante; si falla, la app
  sigue funcionando con el motor propio de deteccion.
- **Firewall:** si usas `ufw` y ya esta activo, el instalador abre el puerto
  automaticamente. Si usas Nginx con `--with-nginx`, recuerda abrir tambien
  el 80 (`sudo ufw allow 80/tcp`).

## Desinstalar

```bash
sudo bash uninstall.sh
```

Te pregunta si borrar tambien los datos de `/opt/nilm`.
