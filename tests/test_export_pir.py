import pandas as pd
import pytest
from export_pir import plant_split, round_preserving_total, sku_split, to_pir

RUN = pd.Timestamp("2026-10-01")
OCT = pd.Timestamp("2026-10-01")


def _sales(rows):
    df = pd.DataFrame(rows, columns=["product_group", "channel_code", "product_code", "warehouse_code", "month", "qty"])
    df["month"] = pd.to_datetime(df["month"])
    return df


def _fc(group="G", channel="BAY", qty=100.0):
    return pd.DataFrame({"product_group": [group], "channel_code": [channel], "target_month": [OCT], "forecast_qty": [qty]})


NO_PHASEOUT = pd.Series(dtype="datetime64[ns]")


def test_sku_split_uses_planner_mix_and_skips_phased_out():
    planner = pd.DataFrame({"product_group": "G", "channel_code": "BAY", "target_month": OCT,
                            "product_code": ["A", "B", "OLD"], "forecast_qty": [30.0, 10.0, 60.0]})
    phaseout = pd.Series({"OLD": pd.Timestamp("2026-06-01")})
    by_sku, unallocated = sku_split(_fc(), planner, _sales([]), RUN, phaseout)
    assert by_sku.set_index("product_code")["forecast_qty"].to_dict() == {"A": 75.0, "B": 25.0}
    assert set(by_sku["split_basis"]) == {"TS"}
    assert unallocated.empty


def test_sku_split_falls_back_to_recent_sales_and_reports_unallocated():
    sales = _sales([("G", "BAY", "A", "MNS", "2026-09-01", 30), ("G", "BAY", "B", "MNS", "2026-08-01", 10),
                    ("G", "BAY", "A", "MNS", "2026-05-01", 999)])  # pencere dışında
    planner = pd.DataFrame({"product_group": pd.Series(dtype=str), "channel_code": pd.Series(dtype=str),
                            "target_month": pd.Series(dtype="datetime64[ns]"), "product_code": pd.Series(dtype=str),
                            "forecast_qty": pd.Series(dtype=float)})
    fc = pd.concat([_fc(), _fc(group="YENI")], ignore_index=True)
    by_sku, unallocated = sku_split(fc, planner, sales, RUN, NO_PHASEOUT)
    assert by_sku.set_index("product_code")["forecast_qty"].to_dict() == {"A": 75.0, "B": 25.0}
    assert set(by_sku["split_basis"]) == {"SATIS"}
    assert unallocated["product_group"].tolist() == ["YENI"]


def test_plant_split_falls_back_to_channel_mix():
    sales = _sales([("G", "BAY", "A", "MNS", "2026-09-01", 3), ("G", "BAY", "A", "IST", "2026-09-01", 1),
                    ("G", "BAY", "X", "ANK", "2026-09-01", 4)])
    by_sku = pd.DataFrame({"product_group": "G", "channel_code": "BAY", "target_month": OCT,
                           "product_code": ["A", "NEW"], "forecast_qty": [40.0, 80.0]})
    out = plant_split(by_sku, sales, RUN).set_index(["product_code", "warehouse_code"])["forecast_qty"]
    assert out[("A", "MNS")] == 30.0 and out[("A", "IST")] == 10.0
    assert out[("NEW", "MNS")] == 30.0 and out[("NEW", "ANK")] == 40.0  # kanalın depo payları 3:1:4
    assert out.sum() == 120.0


def test_round_preserving_total():
    qty = pd.Series([0.4, 0.4, 0.4, 2.5, 2.5])
    out = round_preserving_total(qty, pd.Series(["a", "a", "a", "b", "b"]))
    assert out[:3].sum() == 1 and out[3:].sum() == 5
    assert out.dtype.kind == "i"


def test_to_pir_maps_keys_and_aggregates_channels():
    by_plant = pd.DataFrame({"product_group": "G", "channel_code": ["BAY", "MAG"], "target_month": OCT,
                             "product_code": "A", "warehouse_code": "MNS", "forecast_qty": [10.4, 5.4]})
    materials = pd.DataFrame({"product_code": ["A"], "material": ["000000000000100001"], "base_unit": ["ST"]})
    plants = pd.DataFrame({"warehouse_code": ["MNS"], "plant": ["1000"]})
    pir = to_pir(by_plant, materials, plants, "ML")
    assert pir.to_dict("records") == [{"material": "000000000000100001", "plant": "1000", "version": "ML",
                                       "period_type": "M", "period": "202610", "quantity": 16, "base_unit": "ST"}]


def test_to_pir_refuses_unmapped_codes():
    by_plant = pd.DataFrame({"product_group": "G", "channel_code": "BAY", "target_month": [OCT],
                             "product_code": "A", "warehouse_code": "XXX", "forecast_qty": [1.0]})
    materials = pd.DataFrame({"product_code": ["A"], "material": ["A"], "base_unit": ["ST"]})
    with pytest.raises(ValueError, match="XXX"):
        to_pir(by_plant, materials, pd.DataFrame({"warehouse_code": ["MNS"], "plant": ["1000"]}), "ML")
