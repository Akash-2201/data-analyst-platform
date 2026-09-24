import requests
import pandas as pd
import numpy as np

np.random.seed(42)
dates = pd.date_range('2024-01-01', periods=30, freq='D')
departments = ['Sales', 'Engineering', 'Marketing', 'Finance', 'Support']
regions = ['North', 'South', 'East', 'West']

data = {
    'Date': dates.strftime('%Y-%m-%d'),
    'Department': np.random.choice(departments, 30),
    'Region': np.random.choice(regions, 30),
    'Revenue': np.random.randint(10000, 50000, 30),
    'Expenses': np.random.randint(5000, 30000, 30),
    'Profit': np.random.randint(-5000, 20000, 30),
    'Customers': np.random.randint(50, 500, 30),
    'Latitude': np.random.uniform(12.0, 28.0, 30).round(4),
    'Longitude': np.random.uniform(72.0, 88.0, 30).round(4),
}
df = pd.DataFrame(data)
df.to_csv('test_comprehensive.csv', index=False)

BASE = 'http://localhost:8000'
with open('test_comprehensive.csv', 'rb') as f:
    r = requests.post(f'{BASE}/upload', files={'file': ('comprehensive.csv', f, 'text/csv')})
res = r.json()
did = res['dataset_id']
print('Uploaded Dataset ID:', did)

types_to_test = [
    ('bar', {'x': 'Department', 'y': 'Revenue', 'agg': 'sum'}),
    ('line', {'x': 'Date', 'y': 'Revenue', 'agg': 'mean'}),
    ('scatter', {'x': 'Revenue', 'y': 'Expenses', 'agg': 'count'}),
    ('pie', {'x': 'Department', 'agg': 'count'}),
    ('histogram', {'x': 'Revenue'}),
    ('box_plot', {'x': 'Revenue', 'y': 'Department'}),
    ('stacked_bar', {'x': 'Department', 'y': 'Region'}),
    ('stacked_bar_100', {'x': 'Department', 'y': 'Region'}),
    ('area', {'x': 'Date', 'y': 'Revenue', 'agg': 'sum'}),
    ('treemap', {'x': 'Department', 'y': 'Revenue', 'agg': 'sum'}),
    ('waterfall', {'x': 'Department', 'y': 'Profit'}),
    ('funnel', {'x': 'Department'}),
    ('heatmap', {}),
    ('kpi', {'x': 'Revenue', 'agg': 'sum'}),
    ('forecast_line', {'x': 'Date', 'y': 'Revenue'}),
    ('forecast_ci', {'x': 'Date', 'y': 'Revenue'}),
    ('forecast_actual', {'x': 'Date', 'y': 'Revenue'}),
    ('forecast_residual', {'x': 'Date', 'y': 'Revenue'}),
    ('map', {'x': 'Longitude', 'y': 'Latitude'}),
]

success_count = 0
for ctype, params in types_to_test:
    p = dict(params)
    p['chart_type'] = ctype
    res = requests.get(f'{BASE}/datasets/{did}/chart-data', params=p)
    if res.status_code == 200:
        j = res.json()
        cnt = j.get('group_count')
        print(f"[OK] {ctype:20s} -> 200 OK (count={cnt})")
        success_count += 1
    else:
        print(f"[FAIL] {ctype:18s} -> {res.status_code}: {res.text}")

print(f"\nSummary: {success_count}/{len(types_to_test)} chart types verified.")
