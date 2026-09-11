import sys
import io
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

from dulwich import porcelain
from dulwich.repo import Repo
from dulwich.objects import Tree

r = Repo('.')
out = []


def tree_files(tree_id, prefix=''):
    files
    t = r[tree_id]
    if isinstance(t, Tree):
        for entry in t.items():
            path = prefix + entry.path.decode(errors='replace')
            if isinstance(r[entry.sha], Tree):
                files.update(tree_files(entry.sha, path + '/'))
            else:
                files[path] = entry.sha.hex()
    return files


# 1) Log completo
out.append('=== LOG (mas reciente primero) ===')
for entry in r.get_walker():
    c = entry.commit
    msg = c.message.decode('utf-8', errors='replace').split('\n')[0]
    out.append(f"{c.id.decode()[:12]} | {msg}")

# 2) Archivos en HEAD (arbol final)
head_files = tree_files(r[r.head()].tree)
out.append(f'=== ARCHIVOS EN HEAD ({len(head_files)}) ===')
for p in sorted(head_files):
    out.append('  ' + p)

# 3) Status final
st = porcelain.status(r)
n_staged = len(st.staged.get('add', [])) + len(st.staged.get('modify', [])) + len(st.staged.get('delete', []))
out.append('=== STATUS ===')
out.append(f'staged={n_staged} unstaged={len(st.unstaged)} untracked={len(st.untracked)}')
out.append('HEAD: ' + (r.head().decode() if isinstance(r.head(), bytes) else str(r.head())))

open('scripts/_git_verify.txt', 'w', encoding='utf-8').write('\n'.join(out))