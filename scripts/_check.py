import importlib.util
for m in ("hmmlearn", "sklearn", "pandas", "numpy"):
    print(m, bool(importlib.util.find_spec(m)))
try:
    import hmmlearn
    print("hmmlearn-version:", hmmlearn.__version__)
except Exception as e:
    print("hmmlearn-import-error:", e)
