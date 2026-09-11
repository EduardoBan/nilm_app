import os
import sys
import io
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

from dulwich import porcelain
from dulwich.repo import Repo

r = Repo('.')
out = []

# 1) Identidad local para futuros commits
try:
    cfg = r.get_config()
    cfg.set((b'user',), b'name', b'NILM App')
    cfg.set((b'user',), b'email', b'nilm@local')
    cfg.write_to_path()
    out.append('config user: NILM App <nilm@local>')
except Exception as e:
    out.append('config error: ' + repr(e))

# 2) Archivos a registrar
paths = [
    'backend/data_manager.py',
    'backend/nilm_engine.py',
    'backend/server.py',
    'frontend/css/styles.css',
    'frontend/dist/bundle.js',
    'frontend/index.html',
    'frontend/src/app.ts',
    'frontend/src/components/ChartEngine.ts',
    'frontend/src/types/nilm.ts',
    'tests/__init__.py',
    'tests/test_engine.py',
    'tests/test_labels.py',
]

for p in paths:
    if not os.path.exists(p):
        out.append('MISSING: ' + p)

porcelain.add(r, paths=paths)
out.append('staged: ' + str(len(paths)))

# 3) Commit
msg = """Fix crash en etiquetas/informes y render del Gantt (Linea de Tiempo)

BACKEND:
- data_manager: NameError en set_label (return dict(bucket)); caché RAM con
  LRU (limite 4); escritura atomica + lock de load_labels.json; list_datasets
  incluye .xls; cache_dir dentro del proyecto; get_slug case-insensitive.
- server: import pathlib.Path faltante (ReportHandler), validacion de
  parametros de /api/analyze (400/404), limite 100 MB en uploads.
- nilm_engine: detect_events devuelve tupla (df_work, events) como contrato;
  cluster_appliances auto-reduce K y gestiona pocos/nulos eventos;
  disaggregate_load empareja ON/OFF contra el pool GLOBAL por magnitud
  (~nominal_p) y emite end_time siempre; analyze_dataset devuelve 'warning'
  (+ end_time en ramas FHMM).

FRONTEND:
- app.ts: escapeHtml contra XSS en nombres Ground-Truth, normalizacion
  Number(machine_id) en Gantt, estado-vacio con warning del backend, mapeo
  state_name <- state (FHMM), toast con numero de intervalos.
- ChartEngine.ts: filtros por Number() en Gantt y Operation Level Lines;
  hover con requestAnimationFrame (menos redibujos).
- styles.css: estilos .levels-* (Operation Level Lines) y .gantt-empty,
  .empty-state.
- index.html: cache-busting v=gantt-fix-20260910.

TESTS:
- Suite inicial pytest: labels (set/clear, limite 80, dataset inexistente,
  slug/cache) y motor (eventos, clustering, timeline).

Validado: py_compile OK, 7 tests en verde, analyze_dataset (kmeans y FHMM)
con 300 intervalos y machine_ids coherentes sobre coop_gouge_v2_10_abril.
"""

author = b'NILM App <nilm@local>'
sha = porcelain.commit(r, message=msg.encode('utf-8'), author=author, committer=author)
out.append('COMMIT: ' + (sha.decode() if isinstance(sha, bytes) else str(sha)))

# 4) Verificacion
st = porcelain.status(r)
out.append('after staged:    ' + str(len(st.staged.get('add', [])) + len(st.staged.get('modify', [])) + len(st.staged.get('delete', []))))
out.append('after unstaged:  ' + str(len([p for p in st.unstaged if b'__pycache__' not in p])))
out.append('after untracked: ' + str(len(st.untracked)))
head = r.head()
out.append('HEAD: ' + (head.decode() if isinstance(head, bytes) else str(head)))

open('scripts/_git_commit.txt', 'w', encoding='utf-8').write('\n'.join(out))