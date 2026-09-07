"""Temporal server import test."""
from backend.server import make_app
app = make_app()
# Verify all route patterns are registered (incl. new /api/labels)
patterns = []
for host_spec in app.handlers:
    for spec in host_spec.handler_spec:
        pat = getattr(spec[0], 'pattern', None) if isinstance(spec, tuple) else None
        if pat:
            patterns.append(str(pat))
print("ROUTES:", patterns)
assert any('/api/labels' in p for p in patterns), "Ruta /api/labels no registrada"
print("SERVER_IMPORT_OK")