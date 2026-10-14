#!/usr/bin/env bash
#
# =============================================================================
#  Desinstalador de la Plataforma NILM Energy Analytics (Ubuntu Server)
# =============================================================================
#  Detiene y deshabilita el servicio, elimina la unidad systemd, borra el
#  sitio de Nginx (si existe) y pregunta si eliminar los datos en /opt/nilm.
#
#  Uso:   sudo bash uninstall.sh
# =============================================================================

set -euo pipefail

APP_NAME="nilm"
APP_USER="nilm"
APP_DIR="/opt/nilm"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

if [[ "${EUID}" -ne 0 ]]; then
    echo -e "${RED}[x]${NC} Debes ejecutar como root:  sudo bash uninstall.sh" >&2
    exit 1
fi

# --- 1. Detener y deshabilitar el servicio ----------------------------------
if systemctl list-unit-files | grep -q "${APP_NAME}.service"; then
    log "Deteniendo el servicio '${APP_NAME}'..."
    systemctl stop "${APP_NAME}" 2>/dev/null || true
    systemctl disable "${APP_NAME}" 2>/dev/null || true
    rm -f "/etc/systemd/system/${APP_NAME}.service"
    systemctl daemon-reload
    log "Servicio y unidad systemd eliminados."
else
    warn "El servicio '${APP_NAME}' no estaba instalado."
fi

# --- 2. Quitar el sitio de Nginx si existe ----------------------------------
if [ -f "/etc/nginx/sites-enabled/${APP_NAME}" ]; then
    log "Eliminando configuracion de Nginx..."
    rm -f "/etc/nginx/sites-enabled/${APP_NAME}"
    rm -f "/etc/nginx/sites-available/${APP_NAME}"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || warn "No se pudo recargar Nginx."
    log "Nginx limpio."
fi

# --- 3. Preguntar por los datos ---------------------------------------------
echo
if [ -d "${APP_DIR}" ]; then
    warn "La carpeta ${APP_DIR} contiene la app Y los datos (Data/, cache/, reports/)."
    read -r -p "Eliminar TODO ${APP_DIR} incluyendo datos? [s/N]: " RESP
    case "${RESP}" in
        [sSyY])
            rm -rf "${APP_DIR}"
            log "Carpeta ${APP_DIR} eliminada."
            ;;
        *)
            warn "Se conserva ${APP_DIR}. Puedes borrarlo manualmente cuando quieras."
            ;;
    esac
fi

# --- 4. Usuario del sistema (informativo) -----------------------------------
if id -u "${APP_USER}" >/dev/null 2>&1; then
    warn "El usuario '${APP_USER}' se conserva. Para borrarlo:  userdel ${APP_USER}"
fi

echo
log "Desinstalacion completada."
