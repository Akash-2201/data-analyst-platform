# Data-Cleaning Quality Improvement Progress (70% -> 90%+)

## Scope & Do-No-Harm Contract
- **Project Root**: `c:\Users\j9698\OneDrive\Desktop\data-analyst-platform\data-analyst-platform`
- **Allowed Files**:
  - `CLEAN_PROGRESS.md`
  - `backend/tests/cleaning_eval/*`
  - `backend/app/cleaning.py`
  - `backend/app/validation_rules.py`
  - `backend/app/ai_suggestions.py`
  - `backend/app/profiling.py`
  - `backend/tests/*`
  - (Optional Step 5): Download cleaning log button
- **Hard Gates**:
  - G1: Never fabricate missing/unknown values.
  - G2: Never delete rows except exact duplicates.
  - G3: Byte-identical preservation for valid cells.
  - G4: Every change logged; every blanked cell flagged.
  - G5: Idempotency (0 changes, 0 flags on rerun).
  - G6: Confidence tiers (>=0.90 prechecked; 0.60-0.89 unchecked; <0.60 flag only).
  - G7: Revert if step lowers score or causes collateral damage.
  - G8: Graceful fallback when Gemini is unavailable.

## Progress Tracking

| Step | Description | Status | Score | Collateral | Idempotent | Pristine | Commit |
|------|-------------|--------|-------|------------|------------|----------|--------|
| STEP 0 | Baseline + Scoring Harness | DONE | 24.5% | 31 cells | PASS | PASS | clean-eval: baseline + harness |
| STEP 1 | Safe Foundations (whitespace, tokens, numbers, Int64) | NOT_STARTED | - | - | - | - | - |
| STEP 2 | Type Rules (Name, Email, Phone, Date, Bounds) | NOT_STARTED | - | - | - | - | - |
| STEP 3 | Categorical / City / Category Clustering | NOT_STARTED | - | - | - | - | - |
| STEP 4 | Duplicates, Keys, Row Safety | NOT_STARTED | - | - | - | - | - |
| STEP 5 | Cleaning Log + Flag Hygiene | NOT_STARTED | - | - | - | - | - |
| STEP 6 | Hardening & Final Verification | NOT_STARTED | - | - | - | - | - |

### Baseline Score Table (messy_project_testing_dataset_120_rows.xlsx)
```
=========================================================================================================
Error Class / Category           |  Inj | Fixed | Flagged | Sil.Kept | Sil.Wrong | Del.Wrong | Score %
---------------------------------------------------------------------------------------------------------
Age                              |    4 |     1 |       0 |        3 |         0 |         0 |   25.0%
Amount                           |    2 |     0 |       1 |        1 |         0 |         0 |   50.0%
Category                         |    3 |     0 |       0 |        3 |         0 |         0 |    0.0%
City                             |    5 |     0 |       0 |        4 |         1 |         0 |    0.0%
Coordinates                      |    5 |     0 |       0 |        5 |         0 |         0 |    0.0%
Customer_Name                    |    5 |     1 |       0 |        1 |         3 |         0 |   20.0%
Duplicates                       |    3 |     3 |       0 |        0 |         0 |         0 |  100.0%
Email                            |    6 |     1 |       0 |        3 |         0 |         2 |   16.7%
ID Collision                     |    2 |     0 |       0 |        2 |         0 |         0 |    0.0%
Missing Values (Row Retention)   |    2 |     0 |       0 |        0 |         0 |         2 |    0.0%
Phone                            |    3 |     0 |       0 |        3 |         0 |         0 |    0.0%
Purchase_Date                    |    5 |     3 |       0 |        2 |         0 |         0 |   60.0%
Quantity                         |    3 |     0 |       2 |        1 |         0 |         0 |   66.7%
Row Count                        |    1 |     0 |       0 |        0 |         0 |         1 |    0.0%
---------------------------------------------------------------------------------------------------------
TOTAL OVERALL                    |   49 |     9 |       3 |       28 |         4 |         5 |   24.5%
=========================================================================================================
Overall SCORE : 24.49% (Target: >= 90.0%)
COLLATERAL    : 31 cells altered (Target: 0)
Idempotency   : PASS (0 changes, 0 flags added)
Pristine Data : PASS (0 changes, 0 flags added)
=========================================================================================================
```
