#!/usr/bin/env bash
#
# =============================================================================
#  Instalador de la Plataforma NILM Energy Analytics para Ubuntu Server 24.04
# =============================================================================
#  Que hace este script:
#    1. Verifica que el sistema es Ubuntu y que se ejecuta como root.
#    2. Instala dependencias del sistema (Python 3.12, venv, git, build-essential).
#    3. Crea un usuario de sistema 'nilm' sin capacidad de login.
#    4. Copia la aplicacion a /opt/nilm.
#    5. Crea un entorno virtual en /opt/nilm/venv e instala las dependencias
#       Python (numpy, pandas, scikit-learn, scipy, tornado, hmmlearn,
#       matplotlib, openpyxl). nilmtk (desde Git) se instala de forma
#       TOLERANTE: si falla, la instalacion continua (el motor degrada solo).
#    6. Instala y habilita un servicio systemd 'nilm' que arranca solo.
#    7. Deja la app escuchando en http://<IP-del-servidor>:8000
#
#  Uso:
#       sudo bash install.sh                 # instalacion completa
#       sudo bash install.sh --with-nginx    # ademas instala y configura Nginx
#       sudo bash install.sh --port 8080     # cambia el puerto (por defecto 8000)
#       sudo bash install.sh --no-start      # instala pero no arranca el servicio
#
#  Es IDEMPOTENTE: puede ejecutarse varias veces para actualizar la app.
# =============================================================================

set -euo pipefail

# --- Configuracion por defecto (modificable por flags) ----------------------
APP_NAME="nilm"
APP_USER="nilm"
APP_DIR="/opt/nilm"
APP_PORT="8000"
WITH_NGINX="no"
AUTO_START="yes"
PYTHON_BIN="python3"

# --- Colores para la salida -------------------------------------------------
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; NC=''
fi

log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*" >&2; }
info()  { echo -e "${BLUE}[i]${NC} $*"; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# --- Parseo de argumentos ---------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-nginx) WITH_NGINX="yes"; shift ;;
        --no-start)   AUTO_START="no"; shift ;;
        --port)       APP_PORT="${2:?--port requiere un valor}"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) error "Argumento desconocido: $1"; exit 1 ;;
    esac
done

# =============================================================================
#  1. Comprobaciones previas
# =============================================================================
step "Comprobando requisitos del sistema"

if [[ "${EUID}" -ne 0 ]]; then
    error "Este script debe ejecutarse como root. Usa:  sudo bash install.sh"
    exit 1
fi

# Detecta la distribucion (informativo; no aborta si no es Ubuntu exacto).
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    info "Distribucion detectada: ${PRETTY_NAME:-desconocida}"
    case "${ID:-}" in
        ubuntu) : ;;
        debian) warn "Estas en Debian, no en Ubuntu. Puede funcionar, pero no esta probado." ;;
        *) warn "Distribucion '${ID:-?}' no verificada. Continuando bajo tu responsabilidad." ;;
    esac
fi

# Directorio donde reside este instalador (contiene nilm.service, etc.).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Directorio fuente de la aplicacion: la raiz del repo (3 niveles arriba de
# install/ubuntu/install.sh -> repo/).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

log "Directorio del instalador : ${SCRIPT_DIR}"
log "Directorio de la app      : ${REPO_ROOT}"

if [ ! -f "${REPO_ROOT}/start_server.py" ]; then
    error "No se encontro start_server.py en ${REPO_ROOT}."
    error "Asegurate de copiar toda la carpeta del proyecto al servidor."
    exit 1
fi

# =============================================================================
#  2. Dependencias del sistema
# =============================================================================
step "Instalando dependencias del sistema (apt)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    git \
    build-essential \
    curl \
    ca-certificates

# Verifica la version de Python.
PY_VER="$(${PYTHON_BIN} -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "Python del sistema: ${PY_VER}"
if ${PYTHON_BIN} -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    log "Version de Python compatible (>= 3.10)."
else
    error "Se requiere Python >= 3.10. Version actual: ${PY_VER}"
    exit 1
fi

# =============================================================================
#  3. Usuario de sistema dedicado
# =============================================================================
step "Creando usuario de sistema '${APP_USER}'"
if id -u "${APP_USER}" >/dev/null 2>&1; then
    log "El usuario '${APP_USER}' ya existe."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
    log "Usuario '${APP_USER}' creado (sin login)."
fi

# =============================================================================
#  4. Copiar la aplicacion a /opt/nilm
# =============================================================================
step "Desplegando la aplicacion en ${APP_DIR}"
mkdir -p "${APP_DIR}"

# Copia el codigo fuente (backend, frontend, scripts, arranque).
for item in start_server.py backend frontend scripts; do
    if [ -e "${REPO_ROOT}/${item}" ]; then
        rm -rf "${APP_DIR:?}/${item}"
        cp -r "${REPO_ROOT}/${item}" "${APP_DIR}/${item}"
        log "Copiado: ${item}"
    else
        warn "No se encontro '${item}' en el repo; se omite."
    fi
done

# Copia el requirements del servidor si existe junto al instalador.
if [ -f "${SCRIPT_DIR}/requirements-server.txt" ]; then
    cp "${SCRIPT_DIR}/requirements-server.txt" "${APP_DIR}/requirements-server.txt"
    log "Copiado: requirements-server.txt"
fi

# Carpetas de datos/runtime que la app espera.
mkdir -p "${APP_DIR}/Data" "${APP_DIR}/cache" "${APP_DIR}/reports"

# Limpieza de caches de Python copiados por error.
find "${APP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${APP_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true

# =============================================================================
#  5. Entorno virtual + dependencias Python
# =============================================================================
step "Creando el entorno virtual Python"
if [ ! -x "${APP_DIR}/venv/bin/python" ]; then
    "${PYTHON_BIN}" -m venv "${APP_DIR}/venv"
    log "Entorno virtual creado en ${APP_DIR}/venv"
else
    log "Entorno virtual ya existe; se reutiliza."
fi

VENV_PY="${APP_DIR}/venv/bin/python"
VENV_PIP="${APP_DIR}/venv/bin/pip"

step "Actualizando pip"
"${VENV_PIP}" install --upgrade pip wheel setuptools

step "Instalando dependencias Python (puede tardar varios minutos)"
REQ_FILE="${APP_DIR}/requirements-server.txt"
if [ ! -f "${REQ_FILE}" ]; then
    # Fallback: reconstruye un requirements minimo si no se copio.
    REQ_FILE="${APP_DIR}/requirements.txt"
    cat > "${REQ_FILE}" <<'EOF'
numpy>=1.24
pandas>=2.0
scikit-learn>=1.3
scipy>=1.11
openpyxl>=3.1
tornado>=6.4
hmmlearn>=0.3.0
matplotlib>=3.7
EOF
fi

# Instala el nucleo (si falla aqui es un error real -> abortar).
if ! "${VENV_PIP}" install -r "${REQ_FILE}"; then
    error "Fallo la instalacion de las dependencias principales."
    error "Revisa la conexion a internet y los mensajes anteriores."
    exit 1
fi
log "Dependencias principales instaladas."

# --- nilmtk (OPCIONAL, tolerante a fallos) -----------------------------------
# Se instala desde Git. Si falla, el motor continua sin el (ver nilm_engine.py).
step "Instalando nilmtk (opcional, tolerante a fallos)"
if "${VENV_PY}" -c 'import nilmtk' >/dev/null 2>&1; then
    log "nilmtk ya esta instalado."
elif "${VENV_PIP}" install "git+https://github.com/nilmtk/nilmtk.git"; then
    log "nilmtk instalado correctamente."
else
    warn "No se pudo instalar nilmtk. La app seguira funcionando sin el"
    warn "pipeline de NILMTK (degradado al detector propio del motor)."
fi

# =============================================================================
#  6. Permisos
# =============================================================================
step "Ajustando permisos de ${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"

# =============================================================================
#  7. Servicio systemd
# =============================================================================
step "Instalando el servicio systemd '${APP_NAME}'"
SERVICE_SRC="${SCRIPT_DIR}/${APP_NAME}.service"
SERVICE_DST="/etc/systemd/system/${APP_NAME}.service"

if [ ! -f "${SERVICE_SRC}" ]; then
    error "No se encontro ${SERVICE_SRC}. No se puede instalar el servicio."
    exit 1
fi

# Ajusta el puerto en la unidad segun el flag --port.
cp "${SERVICE_SRC}" "${SERVICE_DST}"
if [ "${APP_PORT}" != "8000" ]; then
    sed -i "s/NILM_PORT=8000/NILM_PORT=${APP_PORT}/" "${SERVICE_DST}"
    log "Puerto del servicio ajustado a ${APP_PORT}."
fi

systemctl daemon-reload
systemctl enable "${APP_NAME}.service"
log "Servicio '${APP_NAME}.service' habilitado (arrancara con el sistema)."

if [ "${AUTO_START}" = "yes" ]; then
    systemctl restart "${APP_NAME}.service"
    sleep 3
    if systemctl is-active --quiet "${APP_NAME}.service"; then
        log "Servicio '${APP_NAME}' iniciado correctamente."
    else
        warn "El servicio no arranco. Revisa:  journalctl -u ${APP_NAME} -n 50"
    fi
else
    log "Servicio instalado pero NO iniciado (--no-start)."
    log "Para iniciarlo:  sudo systemctl start ${APP_NAME}"
fi

# =============================================================================
#  8. Firewall (ufw) - informativo, solo si ya esta activo
# =============================================================================
if command -v ufw >/dev/null 2>&1; then
    if ufw status 2>/dev/null | grep -q "Status: active"; then
        step "Abriendo el puerto ${APP_PORT} en el firewall (ufw)"
        ufw allow "${APP_PORT}/tcp" || warn "No se pudo abrir el puerto en ufw."
    fi
fi

# =============================================================================
#  9. Nginx (opcional, reverse proxy en el puerto 80)
# =============================================================================
if [ "${WITH_NGINX}" = "yes" ]; then
    step "Instalando y configurando Nginx (reverse proxy)"
    apt-get install -y --no-install-recommends nginx
    NGINX_CONF_SRC="${SCRIPT_DIR}/nginx-nilm.conf"
    NGINX_CONF_DST="/etc/nginx/sites-available/${APP_NAME}"
    if [ -f "${NGINX_CONF_SRC}" ]; then
        cp "${NGINX_CONF_SRC}" "${NGINX_CONF_DST}"
        sed -i "s/PROXYPORT/${APP_PORT}/g" "${NGINX_CONF_DST}"
        ln -sf "${NGINX_CONF_DST}" "/etc/nginx/sites-enabled/${APP_NAME}"
        nginx -t && systemctl reload nginx
        log "Nginx configurado. La app queda accesible en http://<IP>/"
    else
        warn "No se encontro ${NGINX_CONF_SRC}; se omite la config de Nginx."
    fi
fi

# =============================================================================
#  Resumen final
# =============================================================================
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo -e "${BOLD}============================================================${NC}"
echo -e "${GREEN} Instalacion completada.${NC}"
echo -e "${BOLD}============================================================${NC}"
if [ "${WITH_NGINX}" = "yes" ]; then
    echo -e "  URL de acceso : ${BOLD}http://${SERVER_IP:-IP-del-servidor}/${NC}  (via Nginx)"
else
    echo -e "  URL de acceso : ${BOLD}http://${SERVER_IP:-IP-del-servidor}:${APP_PORT}/${NC}"
fi
echo -e "  Directorio    : ${APP_DIR}"
echo -e "  Datos         : ${APP_DIR}/Data   (aqui van los .xlsx/.csv)"
echo -e "  Servicio      : systemctl {start|stop|restart|status} ${APP_NAME}"
echo -e "  Logs en vivo  : journalctl -u ${APP_NAME} -f"
echo -e "${BOLD}============================================================${NC}"
echo
info "Para subir datos: copia tus archivos a ${APP_DIR}/Data y luego:"
info "    sudo chown -R ${APP_USER}:${APP_USER} ${APP_DIR}/Data"
info "    sudo systemctl restart ${APP_NAME}"
echo




