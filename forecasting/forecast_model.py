from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "output"
SEASON = 12
HORIZON = 5
BACKTEST_MONTHS = 6
GAP = 2


def clean_sales(sales: pd.DataFrame, channel_codes) -> pd.DataFrame:
    """etl.usp_load_fact_sales ile aynı kurallar: eksik tarih/adet satırları atılır, aynı
    fatura + ürün için ilk satır tutulur, kanal master'ında olmayan kanallar modele alınmaz
    (DW'de -1 / Bilinmeyen kanala bağlanır)."""
    s = sales.dropna(subset=["invoice_date", "qty"])
    s = s.drop_duplicates(subset=["invoice_no", "product_code"])
    return s[s["channel_code"].isin(set(channel_codes))]


def load_sales() -> pd.DataFrame:
    products = pd.read_csv(RAW / "product_snapshot_2025_07.csv")[["product_code", "product_group"]]
    channels = pd.read_csv(RAW / "channel.csv")["channel_code"]
    sales = clean_sales(pd.read_csv(RAW / "sales.csv"), channels)
    sales = sales.merge(products, on="product_code", how="left")
    sales["month"] = pd.to_datetime(sales["invoice_date"]).dt.to_period("M").dt.to_timestamp()
    return sales


def load_monthly() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Gerçekleşen, lag-1 planlama TS'si ve en güncel TS versiyonu (ileri tahmin için)."""
    products = pd.read_csv(RAW / "product_snapshot_2025_07.csv")[["product_code", "product_group"]]
    sales = load_sales()
    actual = (sales.groupby(["product_group", "channel_code", "month"])["qty"].sum()
                   .unstack("month", fill_value=0))

    ts = pd.read_csv(RAW / "forecast.csv", parse_dates=["version_month", "target_month"])
    ts = ts.merge(products, on="product_code", how="left")
    lag1 = ts[(ts["target_month"] - ts["version_month"]).dt.days.between(28, 31)]
    planner = (lag1.groupby(["product_group", "channel_code", "target_month"])["forecast_qty"].sum()
                   .unstack("target_month", fill_value=0))
    latest = ts[ts["version_month"] == ts["version_month"].max()]
    planner_latest = (latest.groupby(["product_group", "channel_code", "target_month"])["forecast_qty"].sum()
                            .unstack("target_month", fill_value=0))
    return actual, planner, planner_latest


def seasonal_naive(y: np.ndarray, h: int) -> np.ndarray:
    return np.array([y[len(y) - SEASON + (k % SEASON)] for k in range(h)], dtype=float)


def moving_average(y: np.ndarray, h: int, w: int = 3) -> np.ndarray:
    return np.repeat(y[-w:].mean(), h)


def _holt_winters(y: np.ndarray, h: int, alpha: float, beta: float, gamma: float, phi: float):
    m = SEASON
    level = y[:m].mean()
    trend = (y[m:2 * m].mean() - y[:m].mean()) / m
    season = list(y[:m] - level)
    fitted = np.empty(len(y))
    for t in range(len(y)):
        s = season[t]
        fitted[t] = level + phi * trend + s
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
        season.append(gamma * (y[t] - level) + (1 - gamma) * s)
    n = len(y)
    damp = np.cumsum(phi ** np.arange(1, h + 1))
    fc = np.array([level + damp[k] * trend + season[n + (k % m)] for k in range(h)])
    return fitted, fc


GRID = list(itertools.product([0.1, 0.3, 0.5], [0.0, 0.05, 0.15], [0.05, 0.2, 0.4], [0.9, 0.98]))


def holt_winters(y: np.ndarray, h: int) -> np.ndarray:
    if len(y) < 2 * SEASON:
        return seasonal_naive(y, h)
    best, best_err = None, np.inf
    for a, b, g, p in GRID:
        fitted, fc = _holt_winters(y, h, a, b, g, p)
        err = np.abs(y[SEASON:] - fitted[SEASON:]).sum()
        if err < best_err:
            best, best_err = fc, err
    return best


MODELS = {"SeasonalNaive": seasonal_naive, "MA3": moving_average, "HoltWinters": holt_winters}
HYBRID = "Hibrit(TS+HW)"


def wape(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.abs(pred - actual).sum() / max(actual.sum(), 1e-9))


def backtest(actual: pd.DataFrame, planner: pd.DataFrame) -> pd.DataFrame:
    months = list(actual.columns)
    targets = months[-BACKTEST_MONTHS:]
    rows = []
    for (grp, ch), series in actual.iterrows():
        y_all = series.values.astype(float)
        if y_all[-12:].sum() < 30:
            continue
        for t in targets:
            ti = months.index(t)
            train = y_all[: ti - GAP + 1]
            row = {"target_month": t, "product_group": grp, "channel_code": ch,
                   "actual": y_all[ti],
                   "PlanlamaTS": planner.loc[(grp, ch), t] if (grp, ch) in planner.index and t in planner.columns else 0}
            for name, fn in MODELS.items():
                row[name] = max(0.0, fn(train, GAP)[-1])

            row[HYBRID] = (row["PlanlamaTS"] + row["HoltWinters"]) / 2
            rows.append(row)
    return pd.DataFrame(rows)


def summarize(bt: pd.DataFrame) -> pd.DataFrame:
    out = []
    for name in ["PlanlamaTS", *MODELS, HYBRID]:
        out.append({"model": name,
                    "accuracy_1_minus_wape": round(1 - wape(bt["actual"].values, bt[name].values), 4),
                    "bias": round(float((bt[name] - bt["actual"]).sum() / bt["actual"].sum()), 4)})
    return pd.DataFrame(out).sort_values("accuracy_1_minus_wape", ascending=False)


def next_run_date(actual: pd.DataFrame) -> pd.Timestamp:
    return actual.columns[-1] + pd.DateOffset(months=1)


def backtest_long(bt: pd.DataFrame, run_date: pd.Timestamp) -> pd.DataFrame:
    """Backtest'i dw.fact_ml_backtest grain'ine çevirir: hedef ay × grup × kanal × model."""
    long = bt.melt(id_vars=["target_month", "product_group", "channel_code", "actual"],
                   value_vars=["PlanlamaTS", *MODELS, HYBRID], var_name="model_name", value_name="forecast_qty")
    long.insert(0, "run_date", run_date.strftime("%Y-%m-%d"))
    long["target_month"] = pd.to_datetime(long["target_month"]).dt.strftime("%Y-%m-%d")
    long = long.rename(columns={"actual": "actual_qty"})
    long[["forecast_qty", "actual_qty"]] = long[["forecast_qty", "actual_qty"]].astype(float).round(2)
    return long[["run_date", "target_month", "product_group", "channel_code", "model_name",
                 "forecast_qty", "actual_qty"]]


def forecast_forward(actual: pd.DataFrame, bt: pd.DataFrame, planner_latest: pd.DataFrame) -> pd.DataFrame:
    """Her seri için backtest'te en düşük WAPE'yi veren model seçilir. Hibrit yalnızca
    serinin tüm ufuk için güncel planlama TS'si varsa adaydır."""
    run_date = next_run_date(actual)
    future = [run_date + pd.DateOffset(months=k) for k in range(HORIZON)]
    rows = []
    for (grp, ch), g in bt.groupby(["product_group", "channel_code"]):
        has_ts = (grp, ch) in planner_latest.index and all(t in planner_latest.columns for t in future)
        candidates = [*MODELS, HYBRID] if has_ts else list(MODELS)
        scores = {m: wape(g["actual"].values, g[m].values) for m in candidates}
        best = min(scores, key=scores.get)
        y = actual.loc[(grp, ch)].values.astype(float)
        if best == HYBRID:
            ts = planner_latest.loc[(grp, ch), future].values.astype(float)
            fc = (ts + np.maximum(0, holt_winters(y, HORIZON))) / 2
        else:
            fc = np.maximum(0, MODELS[best](y, HORIZON))
        for t, q in zip(future, fc):
            rows.append({"run_date": run_date.strftime("%Y-%m-%d"), "target_month": t.strftime("%Y-%m-%d"),
                         "product_group": grp, "channel_code": ch, "model_name": best,
                         "forecast_qty": round(float(q), 2)})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    actual, planner, planner_latest = load_monthly()
    bt = backtest(actual, planner)
    summary = summarize(bt)
    fwd = forecast_forward(actual, bt, planner_latest)

    bt.round({c: 2 for c in bt.select_dtypes("number").columns}).to_csv(OUT / "backtest_results.csv", index=False)
    summary.to_csv(OUT / "model_comparison.csv", index=False)
    fwd.to_csv(OUT / "ml_forecast.csv", index=False)
    backtest_long(bt, next_run_date(actual)).to_csv(OUT / "ml_backtest.csv", index=False)

    print(f"Backtest: {bt['target_month'].min():%Y-%m} – {bt['target_month'].max():%Y-%m}, "
          f"{bt.groupby(['product_group', 'channel_code']).ngroups} seri\n")
    print(summary.to_string(index=False))
    print("\nSeçilen model dağılımı:")
    print(fwd.drop_duplicates(["product_group", "channel_code"])["model_name"].value_counts().to_string())
    print(f"\n{len(fwd)} satır ileri tahmin -> {OUT / 'ml_forecast.csv'}")


if __name__ == "__main__":
    main()
