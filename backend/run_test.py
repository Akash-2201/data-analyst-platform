import requests, json

BASE = 'http://127.0.0.1:8000'

# Upload
with open('test_messy_v2.csv', 'rb') as f:
    r = requests.post(f'{BASE}/upload', files={'file': ('test_messy_v2.csv', f, 'text/csv')})
r.raise_for_status()
data = r.json()
did = data['dataset_id']
print(f'Uploaded. dataset_id={did}')
print('Profile columns:')
for c in data.get('columns', []):
    print(f"  {c['name']:<15s} inferred_type={c.get('inferred_type','?')}")

# Get suggestions
r2 = requests.get(f'{BASE}/datasets/{did}/suggestions')
r2.raise_for_status()
suggs = r2.json()
print()
print('=== FULL /suggestions JSON ===')
print(json.dumps(suggs, indent=2))
print()

# Summary
cat_suggs = [s for s in suggs if s['action'] == 'standardize_category']
print(f'Total suggestions: {len(suggs)}')
print(f'standardize_category suggestions: {len(cat_suggs)}')
print()
for s in cat_suggs:
    col = s['params']['column']
    grps = s['params'].get('groups', [])
    vc = s['params'].get('variant_confidences', {})
    mp = s['params'].get('mapping', {})
    print(f'COLUMN: {col}')
    print(f'  groups={len(grps)}, high-conf mappings={len(mp)}, variant_confidences={dict(vc)}')
    for g in grps:
        vlist = [(v['value'], v['confidence']) for v in g['variants']]
        print(f"  canonical={g['canonical']}  variants={vlist}")
    print()

mf_present = any(
    any(v['value'] in ('M', 'F') for v in g['variants'])
    for s in cat_suggs
    for g in s['params'].get('groups', [])
)
print(f'M/F present in any group? {mf_present}')
