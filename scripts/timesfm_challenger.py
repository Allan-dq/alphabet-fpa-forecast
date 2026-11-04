"""Optional challengers: TimesFM 2.5 (200M, Apache-2.0) and TimesFM 3.0 (TimesFM Non-Commercial
License v1.0), both zero-shot on the same backtest.

Not part of `make all` (needs torch and ~2.2 GB of checkpoints from Hugging Face):

    pip install -e ".[timesfm]"
    python scripts/timesfm_challenger.py

TimesFM is used zero-shot: no fine-tuning, the context is each series' own history up to the origin.
Its quantile head returns the 10th-90th percentiles, so the 80% interval is (q10, q90). There is no
95% interval. Results are written to reports/timesfm_challenger.{csv,md} and compared with the
selected statsforecast model and seasonal naive on exactly the same origins, horizons and targets.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import timesfm

from fpa_forecast import forecasting as F
from fpa_forecast.paths import PROCESSED_DIR, REPORTS_DIR
from fpa_forecast.report import SERIES_NAMES, md_table

CHECKPOINT = "google/timesfm-2.5-200m-pytorch"
CHECKPOINT_V3 = "google/timesfm-3.0-pytorch"
H = 4


def load_v25():
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(CHECKPOINT, torch_compile=False)
    model.compile(timesfm.ForecastConfig(max_context=128, max_horizon=32, normalize_inputs=True,
                                         use_continuous_quantile_head=True, force_flip_invariance=True,
                                         infer_is_positive=True, fix_quantile_crossing=True))

    def run(contexts):  # -> point (n, H), q10 (n, H), q90 (n, H); quantile head = mean, q10..q90
        point, quant = model.forecast(horizon=H, inputs=contexts)
        quant = np.asarray(quant)
        return np.asarray(point), quant[:, :, 1], quant[:, :, 9]
    return run


def load_v30():
    # TimesFM 3.0 weights are under the TimesFM Non-Commercial License v1.0 (accepted by the repo owner for
    # this non-commercial, educational project). The weights are downloaded to the local Hugging Face
    # cache and are never redistributed with this repository.
    model = timesfm.TimesFM3Forecaster.from_pretrained(CHECKPOINT_V3, device="cpu")

    def run(contexts):  # predict(): forecast (H,), quantiles (H, 9) = q10..q90
        outs = [model.predict(np.asarray(c, float), horizon=H, return_quantiles=True) for c in contexts]
        point = np.stack([np.asarray(o.forecast) for o in outs])
        quant = np.stack([np.asarray(o.quantiles) for o in outs])
        return point, quant[:, :, 0], quant[:, :, 8]
    return run


def main() -> None:
    t0 = time.time()
    wide = pd.read_csv(PROCESSED_DIR / "alphabet_quarterly_wide.csv")
    meta = json.loads((REPORTS_DIR / "selected_model.json").read_text())
    holdout, cutoffs = meta["holdout_quarter"], meta["backtest_cutoffs"]
    last_actual = str(pd.Period(holdout, freq="Q") - 1)
    h = F.build_hierarchy(wide)
    ids = list(F.ID_TO_LINE)
    bottom_ids = [i for i in h.Y.unique_id.unique() if i.count("/") == 2]
    models = {"TimesFM-2.5": load_v25(), "TimesFM-3.0": load_v30()}

    actual = h.Y.assign(line=h.Y.unique_id.map(F.ID_TO_LINE), fiscal_quarter=h.Y.ds.map(F.ds_to_q))
    rows = []
    for (name, run), c in [(m, c) for m in models.items() for c in cutoffs]:
        train = h.Y[h.Y.ds <= F.q_to_ds(c)]
        series = {uid: g.sort_values("ds")["y"].to_numpy(float) for uid, g in train.groupby("unique_id")}
        order = ids + bottom_ids
        point, q10, q90 = run([series[u] for u in order])
        cut = pd.Period(c, freq="Q")
        fq = [str(cut + k) for k in range(1, H + 1)]
        base = {u: (point[i], q10[i], q90[i]) for i, u in enumerate(order)}
        # BottomUp: sum the leaf medians (intervals: not coherent sums of quantiles, so not reported)
        bu = {}
        for u in ids:
            if u in bottom_ids:
                leaves = [u]
            else:  # "Alphabet" or a segment: every leaf underneath it
                leaves = [b for b in bottom_ids if b.startswith(u + "/")]
            bu[u] = np.sum([base[b][0] for b in leaves], axis=0)
        scale = F.mase_scale(h, c)
        for u in ids:
            line = F.ID_TO_LINE[u]
            for k in range(H):
                rows.append(dict(model=name, method="base", line=line, cutoff=c, fiscal_quarter=fq[k],
                                 horizon=k + 1, forecast=base[u][0][k], lo_80=base[u][1][k], hi_80=base[u][2][k],
                                 lo_95=np.nan, hi_95=np.nan, mase_scale=scale[line]))
                rows.append(dict(model=name, method="BottomUp", line=line, cutoff=c, fiscal_quarter=fq[k],
                                 horizon=k + 1, forecast=bu[u][k], lo_80=np.nan, hi_80=np.nan, lo_95=np.nan,
                                 hi_95=np.nan, mase_scale=scale[line]))
    bt = pd.DataFrame(rows).merge(actual[["line", "fiscal_quarter", "y"]].dropna(subset=["line"])
                                  .rename(columns={"y": "actual"}), on=["line", "fiscal_quarter"], how="inner")
    bt = bt[bt.fiscal_quarter <= last_actual]
    tfm = F.score(bt, ["model", "method", "line"])

    ref = pd.read_csv(REPORTS_DIR / "backtest_per_line.csv")
    keep = [(meta["model"], meta["method"], meta.get("intervals", "model")), ("SeasonalNaive", "base", "model")]
    ref = ref[[(m, k, i) in keep for m, k, i in zip(ref.model, ref.method, ref.intervals)]].drop(columns="intervals")
    allm = pd.concat([tfm, ref], ignore_index=True)
    allm.to_csv(REPORTS_DIR / "timesfm_challenger.csv", index=False)

    summary = (allm.groupby(["model", "method"])
               .agg(mean_mase=("mase", "mean"), mean_wape=("wape", "mean"), coverage_80=("coverage_80", "mean"))
               .reset_index())
    total = allm[allm.line == "total_revenue_ex_hedging"].set_index(["model", "method"])[["wape", "mase"]]
    summary = summary.join(total.add_prefix("total_"), on=["model", "method"]).sort_values("mean_mase")
    wide_mase = allm.pivot_table(index="line", columns=["model", "method"], values="mase")
    wide_mase.columns = [f"{m} / {k}" for m, k in wide_mase.columns]
    wide_mase.index = pd.Index([SERIES_NAMES[i] for i in wide_mase.index], name="Series")
    winner = summary.iloc[0]
    text = f"""# Challengers: TimesFM 2.5 and 3.0 (zero-shot)

Same {len(cutoffs)} origins ({cutoffs[0]} to {cutoffs[-1]}), horizons 1-4, targets up to {last_actual}, same metrics.
Both models are used zero-shot on each series' own history:
- `{CHECKPOINT}` (Apache-2.0);
- `{CHECKPOINT_V3}` (TimesFM Non-Commercial License v1.0, used here for a non-commercial educational project; weights are not redistributed).

Both models output the 10th–90th percentiles, so only 80% coverage is reported. For BottomUp, interval sums are not valid, so no coverage is shown.

{md_table(summary, {'mean_mase': '{:.3f}', 'total_mase': '{:.3f}', 'mean_wape': '{:.1%}', 'total_wape': '{:.1%}', 'coverage_80': '{:.1%}'}, index=False)}

Lowest mean MASE: **{winner.model} / {winner.method}** ({winner.mean_mase:.3f}).
The production model was **not** changed: it was selected by the rule in `backtest_summary.md`, which was fixed before this comparison.

## MASE by series

{md_table(wide_mase, default='{:.2f}')}

Runtime: {time.time() - t0:.0f}s on CPU.
"""
    (REPORTS_DIR / "timesfm_challenger.md").write_text(text)
    print(summary.to_string())


if __name__ == "__main__":
    main()
