"""Compare regenerated numeric outputs with the versions committed in git (HEAD).

Fails if any number moved by more than the tolerance, so CI proves that
`python run_pipeline.py` reproduces the published tables.
"""
import io
import json
import subprocess
import sys

import numpy as np
import pandas as pd

FILES = [
    "reports/backtest_overall.csv",
    "reports/backtest_per_line.csv",
    "reports/pnl_forecast.csv",
    "reports/variance_2026Q3.csv",
    "reports/scenarios.csv",
    "reports/sensitivity_operating_margin.csv",
    "reports/track_record.csv",
    "reports/experiment_e2_cost_of_revenues.csv",
]
RTOL, ATOL = 1e-4, 1e-3
# Conformal intervals are calibrated on refitted cross-validation errors; their interval scores move by
# ~0.1-0.3% between CPU/BLAS builds (seen on Linux CI vs macOS). They are checked at 1%. Everything else,
# including every point metric and the selected configuration's metrics, stays at RTOL.
LOOSE = {"columns": {"msis", "mean_msis"}, "rtol": 1e-2}


def committed(path: str) -> pd.DataFrame:
    raw = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, check=True).stdout
    return pd.read_csv(io.BytesIO(raw))


bad = []
for f in FILES:
    new, old = pd.read_csv(f), committed(f)
    if new.shape != old.shape or list(new.columns) != list(old.columns):
        bad.append(f"{f}: shape/columns changed {old.shape} -> {new.shape}")
        continue
    num = new.select_dtypes("number").columns
    other = [c for c in new.columns if c not in num]
    if not new[other].astype(str).equals(old[other].astype(str)):
        bad.append(f"{f}: non-numeric columns differ")
    rtol = np.full((len(new), len(num)), RTOL)
    if "intervals" in new.columns:
        conformal = (new["intervals"] == "conformal").to_numpy()
        for j, c in enumerate(num):
            if c in LOOSE["columns"]:
                rtol[conformal, j] = LOOSE["rtol"]
    a, b = new[num].to_numpy(float), old[num].to_numpy(float)
    with np.errstate(invalid="ignore"):
        close = (a == b) | (np.abs(a - b) <= ATOL + rtol * np.abs(b)) | (np.isnan(a) & np.isnan(b))
    if not close.all():
        bad.append(f"{f}: {int((~close).sum())} numbers differ beyond rtol={RTOL}")
        rows, cols = np.where(~close)
        for r, c in list(zip(rows, cols))[:25]:
            key = " ".join(str(new.iloc[r][k]) for k in other)
            print(f"   {f} | {key} | {num[c]}: committed={old[num].iloc[r, c]!r} regenerated={new[num].iloc[r, c]!r}")
    print(f"{f}: {'OK' if close.all() else 'DIFF'}")

# The decision itself must be identical on every platform.
sel_new = json.loads(open("reports/selected_model.json").read())
sel_old = json.loads(subprocess.run(["git", "show", "HEAD:reports/selected_model.json"], capture_output=True,
                                    check=True).stdout)
for k in ["model", "method", "intervals"]:
    if sel_new.get(k) != sel_old.get(k):
        bad.append(f"selected configuration changed: {k} {sel_old.get(k)} -> {sel_new.get(k)}")
print(f"selected configuration: {sel_new['model']} + {sel_new['method']} ({sel_new['intervals']} intervals)")

if bad:
    print("\n".join(bad))
    sys.exit(1)
print("all regenerated numbers match the committed outputs")
