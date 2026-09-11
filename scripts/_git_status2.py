import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dulwich import porcelain
from dulwich.repo import Repo

r = Repo('.')
out
st = porcelain.status(r)


def dump(key, obj, is_dict):
    out.append(f'=== {key.upper()} ({len(obj)}) ===')
    if is_dict:
        for p in sorted(obj.keys(), key=str):
            out.append(f'  {str(p)}  [{obj[p]}]')
    else:
        for p in sorted(map(str, obj)):
            out.append(f'  {p}')


dump('staged', st.staged, True)
dump('unstaged', st.unstaged, True)
dump('untracked', st.untracked, False)

open('scripts/_git_status.txt', 'w', encoding='utf-8').write('\n'.join(out))