import numpy as np
import pandas as pd
import pytest
from forecast_model import (
    HYBRID,
    MODELS,
    SEASON,
    _holt_winters,
    backtest_long,
    clean_sales,
    forecast_forward,
    holt_winters,
    moving_average,
    seasonal_naive,
    wape,
)


def seasonal_series(years: int = 3, trend: float = 0.0) -> np.ndarray:
    t = np.arange(years * SEASON)
    return 100 + trend * t + 20 * np.sin(2 * np.pi * t / SEASON)


def test_wape():
    assert wape(np.array([10.0, 10.0]), np.array([12.0, 7.0])) == pytest.approx(0.25)
    assert wape(np.array([0.0]), np.array([0.0])) == 0.0


def test_seasonal_naive_repeats_last_season():
    y = np.arange(24, dtype=float)
    assert seasonal_naive(y, 14).tolist() == [*range(12, 24), 12, 13]


def test_moving_average():
    assert moving_average(np.array([1.0, 2.0, 6.0, 7.0]), 2).tolist() == [5.0, 5.0]


def test_holt_winters_falls_back_to_seasonal_naive_on_short_history():
    y = seasonal_series(years=1) + np.arange(SEASON)
    np.testing.assert_array_equal(holt_winters(y, 5), seasonal_naive(y, 5))


def test_holt_winters_fits_pure_seasonal_series():
    y = seasonal_series(years=3)
    fc = holt_winters(y, SEASON)
    np.testing.assert_allclose(fc, y[:SEASON], rtol=0.02)


def test_holt_winters_follows_trend():
    y = seasonal_series(years=3, trend=2.0)
    fitted, fc = _holt_winters(y, 1, alpha=0.3, beta=0.15, gamma=0.2, phi=0.98)
    assert len(fitted) == len(y)
    assert fc[0] > y[-SEASON]


def test_clean_sales_mirrors_etl_rules():
    sales = pd.DataFrame({
        "invoice_no":   ["F1", "F1", "F2", "F3", "F4"],
        "invoice_date": ["2026-01-05", "2026-01-05", "2026-01-06", None, "2026-01-07"],
        "product_code": ["P1", "P1", "P1", "P1", "P1"],
        "channel_code": ["BAY", "BAY", "XX99", "BAY", "MAG"],
        "qty":          [5, 5, 3, 2, -1],
    })
    out = clean_sales(sales, ["BAY", "MAG"])
    assert out["invoice_no"].tolist() == ["F1", "F4"]  # mükerrer, eksik tarih ve tanımsız kanal elenir
    assert out["qty"].tolist() == [5, -1]              # iade satırı korunur


def _forward_inputs(planner_months: int):
    months = pd.date_range("2024-01-01", periods=36, freq="MS")
    keys = pd.MultiIndex.from_tuples([("G", "BAY")], names=["product_group", "channel_code"])
    actual = pd.DataFrame([seasonal_series(years=3)], index=keys, columns=months)
    future = pd.date_range(months[-1] + pd.DateOffset(months=1), periods=planner_months, freq="MS")
    planner_latest = pd.DataFrame([[500.0] * planner_months], index=keys, columns=future)
    # Backtest'te hibrit kusursuz, diğer modeller hatalı -> hibrit seçilmeli
    bt = pd.DataFrame({"product_group": ["G"] * 2, "channel_code": ["BAY"] * 2, "actual": [100.0, 100.0],
                       **{m: [50.0, 50.0] for m in MODELS}, HYBRID: [100.0, 100.0]})
    return actual, bt, planner_latest


def test_forecast_forward_uses_hybrid_when_planner_ts_covers_horizon():
    actual, bt, planner_latest = _forward_inputs(planner_months=5)
    fwd = forecast_forward(actual, bt, planner_latest)
    assert len(fwd) == 5
    assert set(fwd["model_name"]) == {HYBRID}
    hw = np.maximum(0, holt_winters(actual.iloc[0].values.astype(float), 5))
    np.testing.assert_allclose(fwd["forecast_qty"], np.round((500 + hw) / 2, 2))


def test_forecast_forward_skips_hybrid_without_full_planner_ts():
    actual, bt, planner_latest = _forward_inputs(planner_months=3)
    fwd = forecast_forward(actual, bt, planner_latest)
    assert HYBRID not in set(fwd["model_name"])
    assert fwd["model_name"].nunique() == 1


def test_backtest_long_has_one_row_per_model():
    bt = pd.DataFrame({"target_month": [pd.Timestamp("2026-09-01")], "product_group": ["G"], "channel_code": ["BAY"],
                       "actual": [100.0], "PlanlamaTS": [110.0], **{m: [90.0] for m in MODELS}, HYBRID: [100.004]})
    long = backtest_long(bt, pd.Timestamp("2026-10-01"))
    assert list(long.columns) == ["run_date", "target_month", "product_group", "channel_code", "model_name",
                                  "forecast_qty", "actual_qty"]
    assert sorted(long["model_name"]) == sorted(["PlanlamaTS", *MODELS, HYBRID])
    assert set(long["run_date"]) == {"2026-10-01"} and set(long["target_month"]) == {"2026-09-01"}
    assert (long["actual_qty"] == 100.0).all()
    assert long.loc[long["model_name"] == HYBRID, "forecast_qty"].item() == 100.0
