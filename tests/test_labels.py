"""Smoke tests del backend NILM (sin datos reales): DataManager labels + validaciones.
Ejecutar:  .venv\\Scripts\\python.exe -m pytest tests/ -q
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data_manager import DataManager


def make_dm():
    tmp = tempfile.mkdtemp(prefix="nilm_test_")
    data = os.path.join(tmp, "Data")
    cache = os.path.join(tmp, "cache")
    dm = DataManager(data_dir=data, cache_dir=cache)
    # Aislar labels en el tmp (no toca backend/load_labels.json real)
    dm._labels_file = lambda: os.path.join(tmp, "load_labels.json")
    return dm


def test_set_and_clear_labels():
    dm = make_dm()
    out = dm.set_label("ds1", 0, "Compresor 1")
    assert out == {"0": "Compresor 1"}
    assert dm.get_labels("ds1") == {"0": "Compresor 1"}
    # Vacío limpia
    out = dm.set_label("ds1", 0, "   ")
    assert out == {}
    assert dm.get_labels("ds1") == {}


def test_label_max_length():
    dm = make_dm()
    try:
        dm.set_label("ds1", 1, "x" * 81)
    except ValueError:
        pass
    else:
        raise AssertionError("set_label debería rechazar >80 caracteres")


def test_clear_labels_missing_dataset():
    dm = make_dm()
    assert dm.clear_labels("no_existe") == {}


def test_slug_and_cache_dirs():
    dm = make_dm()
    assert dm.get_slug("Mi Medición.XLSX") == "mi_medición"
    assert os.path.basename(dm.cache_dir) == "cache"
