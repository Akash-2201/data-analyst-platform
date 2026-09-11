from dotenv import load_dotenv
load_dotenv()
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from app.profiling import profile_dataframe
from app.ai_suggestions import generate_ai_suggestions

df = pd.read_excel(r'C:\Users\j9698\OneDrive\Desktop\messy_test_data_20x7.xlsx')
profile = profile_dataframe(df)

print("=== PROFILING COLUMNS ===")
for col in profile["columns"]:
    print(f"Col: {col['name']:10} | dtype: {col['dtype']:10} | inferred_type: {col['inferred_type']}")

print("\n=== GENERATING AI SUGGESTIONS ===")
res = generate_ai_suggestions(df, profile)
print("Source:", res.get("source"))
cols_with_sugg = set()
for s in res.get("suggestions", []):
    col = s.get("params", {}).get("column")
    if col:
        cols_with_sugg.add(col)
    print(f"[{s.get('action')}] col={col} | desc={s.get('description')}")

print("\nColumns with any suggestions:", cols_with_sugg)
all_cols = set(df.columns)
print("Columns missing suggestions:", all_cols - cols_with_sugg)
