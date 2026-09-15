"""Respaldo automatico del proyecto NILM (codigo + datos + historial Git).

Uso:
    python scripts/backup.py            # solo crea el ZIP de respaldo
    python scripts/backup.py --auto     # git add/commit + ZIP en un solo paso
    python scripts/backup.py --keep 10  # numero de respaldos a conservar (def. 5)

Que incluye:
    - Todo el codigo fuente, frontend/dist/bundle.js, tests y scripts.
    - La carpeta Data/ con los Excel de medida (no versionados en Git).
    - La carpeta .git con el historial completo (restaurable tal cual).

Que excluye (regenerable / temporal):
    cache/, __pycache__, *.pyc, node_modules/, backups/ y el propio ZIP.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "backups"

# Carpetas de primer nivel (o patrones) que nunca entran al respaldo.
EXCLUDE_DIRS = {"cache", "__pycache__", "backups", "node_modules", ".pytest_cache", "reports"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip"}


def _should_skip(path: Path) -> bool:
    """True si la ruta esta dentro de una carpeta excluida o tiene sufijo temporal."""
    parts = set(path.relative_to(ROOT).parts)
    if parts & EXCLUDE_DIRS:
        return True
    return path.suffix.lower() in EXCLUDE_SUFFIXES


def _iter_files():
    """Recorre el proyecto devolviendo los ficheros que deben respaldarse."""
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and not _should_skip(path):
            yield path


def run_git_commit() -> str:
    """Hace git add + commit del estado actual. Devuelve un texto de estado."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT, capture_output=True, text=True
        )
    except FileNotFoundError:
        return "git no encontrado en PATH: se omite el commit (solo se hace el ZIP)"

    if inside.returncode != 0:
        return "El proyecto no es un repositorio Git: se omite el commit (solo ZIP)"

    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=False, capture_output=True, text=True)

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    if not status:
        return "Sin cambios pendientes: no se crea commit nuevo"

    msg = f"Respaldo automatico {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    commit = subprocess.run(
        ["git", "commit", "-m", msg], cwd=ROOT, capture_output=True, text=True
    )
    if commit.returncode != 0:
        return f"Commit fallido: {(commit.stderr or commit.stdout).strip()[:200]}"

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    return f"Commit creado: {head} ({msg})"


def make_zip() -> Path:
    """Crea el ZIP con marca de tiempo y devuelve su ruta."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"nilm_app_{stamp}.zip"

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in _iter_files():
            arcname = path.relative_to(ROOT).as_posix()
            try:
                zf.write(path, arcname)
            except OSError as exc:
                print(f"  aviso: no se pudo incluir {arcname}: {exc}")
                continue
            count += 1

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"Respaldo creado: {target}")
    print(f"  ficheros: {count} | tamano: {size_mb:.1f} MB")
    return target


def rotate(keep: int) -> None:
    """Conserva solo los `keep` respaldos mas recientes."""
    backups = sorted(BACKUP_DIR.glob("nilm_app_*.zip"))
    for old in backups[:-keep] if keep > 0 else []:
        try:
            old.unlink()
            print(f"  respaldo antiguo eliminado: {old.name}")
        except OSError as exc:
            print(f"  aviso: no se pudo eliminar {old.name}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Respaldo automatico del proyecto NILM")
    parser.add_argument("--auto", action="store_true",
                        help="hacer git add/commit antes de crear el ZIP")
    parser.add_argument("--keep", type=int, default=5,
                        help="numero de respaldos ZIP a conservar (0 = todos)")
    args = parser.parse_args()

    os.chdir(ROOT)
    print("=" * 65)
    print("  RESPALDO AUTOMATICO - NILM ENERGY ANALYTICS")
    print("=" * 65)

    if args.auto:
        print("[1/3] Control de versiones (Git)")
        print(f"  {run_git_commit()}")
        print("[2/3] Copia de seguridad (ZIP)")
    else:
        print("[1/2] Copia de seguridad (ZIP)")
        print("  (usa --auto para incluir tambien el commit de Git)")

    make_zip()
    rotate(args.keep)
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
