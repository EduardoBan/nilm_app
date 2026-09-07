"""Quick server check: fast endpoints only."""
import urllib.request, json

try:
    with urllib.request.urlopen('http://localhost:8000/api/datasets', timeout=30) as r:
        data = json.loads(r.read().decode('utf-8'))
        print('API_STATUS=200')
        print('DATASETS=', [d['id'] for d in data.get('data', [])])
except Exception as e:
    print('API_ERROR=', e)

try:
    with urllib.request.urlopen('http://localhost:8000/api/labels?dataset_id=coop_gouge_v2_10_abril', timeout=15) as r:
        data = json.loads(r.read().decode('utf-8'))
        print('LABELS_STATUS=200')
        print('LABELS=', data.get('data', {}).get('labels'))
except Exception as e:
    print('LABELS_ERROR=', e)

try:
    with urllib.request.urlopen('http://localhost:8000/', timeout=10) as r:
        html = r.read().decode('utf-8')
        print('FRONTEND_STATUS=200')
        print('HAS_FHMM_CHECKBOX=', 'chk-fhmm' in html)
        print('HAS_BUNDLE_VERSION=', 'fhmm-gt-20260907' in html)
except Exception as e:
    print('FE_ERROR=', e)

print('QUICK_CHECK_DONE')