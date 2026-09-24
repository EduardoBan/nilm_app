"""Copy the installed Python distributions needed by the portable NILM app."""
from __future__ import annotations

import importlib.metadata as metadata
import os
import re
import shutil
import sys
from pathlib import Path

# Lista cerrada: evita arrastrar el entorno completo del equipo (Jupyter,
# Django, etc.) al payload. Incluye las dependencias de importación que
# necesitan los paquetes principales en runtime.
REQUIRED = [
    "numpy", "pandas", "scipy", "scikit-learn", "tornado", "hmmlearn",
    "openpyxl", "matplotlib", "pillow", "requests", "psutil",
    "joblib", "threadpoolctl", "python-dateutil", "pytz", "six",
    "packaging", "cycler", "fonttools", "kiwisolver", "pyparsing",
    "contourpy", "et-xmlfile", "defusedxml", "certifi", "charset-normalizer",
    "idna", "urllib3", "attrs", "pycparser",
]
NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)")


def requirement_name(requirement: str) -> str:
    # Handles "name>=1.2", "name (>=1.2)", "name[extra]==1.2" and URLs.
    match = NAME_RE.match(requirement.strip())
    return match.group(1).replace("_", "-").lower() if match else ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: copy_runtime_packages.py DESTINATION", file=sys.stderr)
        return 2
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    distributions = {}
    for dist in metadata.distributions():
        name = (dist.metadata.get("Name") or "").replace("_", "-").lower()
        if name:
            distributions[name] = dist

    selected = {}
    missing = []
    for name in REQUIRED:
        dist = distributions.get(name)
        if dist is None:
            missing.append(name)
        else:
            selected[name] = dist
    if missing:
        print("Missing distributions: " + ", ".join(missing), file=sys.stderr)
        return 2

    for dist in selected.values():
        dist_root = Path(dist.locate_file(""))
        for entry in dist.files or []:
            source = Path(dist.locate_file(entry)).resolve()
            # Los entry points externos (por ejemplo f2py.exe) viven en
            # prefix\Scripts, fuera de site-packages. No hacen falta para
            # ejecutar la aplicación y no tienen ruta relativa válida.
            try:
                relative = source.relative_to(dist_root.resolve())
            except ValueError:
                continue
            if any(part in {"__pycache__", "tests", "test"} for part in relative.parts):
                continue
            target = destination / relative
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    print("Copied distributions: " + ", ".join(sorted(selected)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
