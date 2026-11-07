"""Model tahminini SAP S/4HANA / ECC Planlanmış Bağımsız İhtiyaç (PIR) seviyesine indirir.

Model ürün grubu × kanal × ay seviyesinde tahmin üretir; PIR ise malzeme × üretim yeri × ay
seviyesindedir. Dağıtım iki adımda yapılır:

1. Grup × kanal -> ürün: en güncel planlama TS versiyonundaki ürün payları (yeni/çıkan ürün
   bilgisi planlamacıda). TS'si olmayan seriler için son SKU_MIX_MONTHS ayın satış payı.
   Hedef aydan önce satıştan kalkmış (phaseout_date) ürünler her iki durumda da dışarıda kalır.
2. Ürün × kanal -> depo: son PLANT_MIX_MONTHS ayın depo payları; ürün × kanalın satışı yoksa
   kanalın depo payları.

Çıktı ayrı bir PIR versiyonuna yüklenecek dosyadır (varsayılan aktif değil, MRP kullanmaz);
planlamacı MD63'te kendi versiyonuyla karşılaştırır.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "forecasting"))
from forecast_model import OUT, RAW, load_sales  # noqa: E402

# Gerçek malzeme / üretim yeri eşlemeleri repoya konmaz: SAP_MAP_DIR ile repo dışındaki bir klasör
# gösterilir. Tanımlı değilse buradaki örnek eşlemeler kullanılır.
MAP_DIR = Path(os.getenv("SAP_MAP_DIR", Path(__file__).resolve().parent))
SKU_MIX_MONTHS = 3
PLANT_MIX_MONTHS = 6
KEYS = ["product_group", "channel_code", "target_month"]


def _shares(df: pd.DataFrame, by: list[str], value: str) -> pd.DataFrame:
    df = df[df[value] > 0].copy()
    df["share"] = df[value] / df.groupby(by)[value].transform("sum")
    return df.drop(columns=value)


def drop_phased_out(df: pd.DataFrame, phaseout: pd.Series) -> pd.DataFrame:
    """Hedef ayda satıştan kalkmış ürün satırlarını atar; `phaseout` ürün koduna göre indekslidir."""
    end = pd.Series(pd.to_datetime(phaseout).reindex(df["product_code"]).to_numpy(), index=df.index)
    return df[end.isna() | (end > pd.to_datetime(df["target_month"]))]


def sku_split(forecast: pd.DataFrame, planner_latest: pd.DataFrame, sales: pd.DataFrame,
              run_date: pd.Timestamp, phaseout: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grup × kanal × ay tahminini ürüne dağıtır; dağıtılamayan seriler ikinci değer olarak döner."""
    ts = _shares(drop_phased_out(planner_latest, phaseout), KEYS, "forecast_qty")[[*KEYS, "product_code", "share"]]

    recent = sales[(sales["month"] >= run_date - pd.DateOffset(months=SKU_MIX_MONTHS)) & (sales["month"] < run_date)]
    mix = recent.groupby(["product_group", "channel_code", "product_code"], as_index=False)["qty"].sum()
    mix = _shares(mix, ["product_group", "channel_code"], "qty")

    has_ts = forecast.merge(ts[KEYS].drop_duplicates(), on=KEYS, how="left", indicator=True)["_merge"].eq("both").values
    by_ts = forecast[has_ts].merge(ts, on=KEYS)
    by_mix = forecast[~has_ts].merge(mix, on=["product_group", "channel_code"], how="left", indicator=True)
    unallocated = by_mix[by_mix["_merge"] == "left_only"][forecast.columns]
    by_mix = by_mix[by_mix["_merge"] == "both"].drop(columns="_merge")
    by_mix = drop_phased_out(by_mix, phaseout)
    by_mix["share"] = by_mix["share"] / by_mix.groupby(KEYS)["share"].transform("sum")

    out = pd.concat([by_ts.assign(split_basis="TS"), by_mix.assign(split_basis="SATIS")], ignore_index=True)
    out["forecast_qty"] = out["forecast_qty"] * out["share"]
    return out.drop(columns="share"), unallocated


def plant_split(by_sku: pd.DataFrame, sales: pd.DataFrame, run_date: pd.Timestamp) -> pd.DataFrame:
    recent = sales[(sales["month"] >= run_date - pd.DateOffset(months=PLANT_MIX_MONTHS)) & (sales["month"] < run_date)]
    sku_mix = _shares(recent.groupby(["product_code", "channel_code", "warehouse_code"], as_index=False)["qty"].sum(),
                      ["product_code", "channel_code"], "qty")
    ch_mix = _shares(recent.groupby(["channel_code", "warehouse_code"], as_index=False)["qty"].sum(),
                     ["channel_code"], "qty")

    known = by_sku.merge(sku_mix[["product_code", "channel_code"]].drop_duplicates(), how="left", indicator=True)
    known = known["_merge"].eq("both").values
    out = pd.concat([by_sku[known].merge(sku_mix, on=["product_code", "channel_code"]),
                     by_sku[~known].merge(ch_mix, on="channel_code")], ignore_index=True)
    out["forecast_qty"] = out["forecast_qty"] * out["share"]
    return out.drop(columns="share")


def round_preserving_total(qty: pd.Series, groups: pd.Series) -> pd.Series:
    """Tam sayıya yuvarlar; her grubun yuvarlanmış toplamı, ondalıklı toplamının yuvarlanmışına eşit kalır."""
    out = np.floor(qty)
    remainder = qty - out
    for _, idx in qty.groupby(groups).groups.items():
        missing = int(round(qty[idx].sum() - out[idx].sum()))
        if missing > 0:
            out[remainder[idx].nlargest(missing).index] += 1
    return out.astype(int)


def to_pir(by_plant: pd.DataFrame, materials: pd.DataFrame, plants: pd.DataFrame, version: str) -> pd.DataFrame:
    """SAP anahtarlarına eşler; eşlenemeyen kod varsa hata verir (sessizce düşürmez)."""
    missing_mat = sorted(set(by_plant["product_code"]) - set(materials["product_code"]))
    missing_plant = sorted(set(by_plant["warehouse_code"]) - set(plants["warehouse_code"]))
    if missing_mat or missing_plant:
        raise ValueError(f"Eşleme eksik — ürün: {missing_mat}, depo: {missing_plant}")

    df = by_plant.merge(materials, on="product_code").merge(plants, on="warehouse_code")
    df = df.groupby(["product_group", "material", "plant", "base_unit", "target_month"], as_index=False)["forecast_qty"].sum()
    df["quantity"] = round_preserving_total(df["forecast_qty"], df["product_group"] + "|" + df["target_month"].astype(str))
    df["period"] = pd.to_datetime(df["target_month"]).dt.strftime("%Y%m")
    df["version"] = version
    df["period_type"] = "M"
    return df[["material", "plant", "version", "period_type", "period", "quantity", "base_unit"]]


def main() -> None:
    ap = argparse.ArgumentParser(description="ML tahminini SAP PIR yükleme dosyasına çevirir")
    ap.add_argument("--version", default="ML", help="PIR ihtiyaç versiyonu (VERSB), varsayılan ML")
    ap.add_argument("--out", type=Path, default=OUT / "sap_pir_upload.csv")
    args = ap.parse_args()

    forecast = pd.read_csv(OUT / "ml_forecast.csv", parse_dates=["run_date", "target_month"])
    run_date = forecast["run_date"].max()
    forecast = forecast[forecast["run_date"] == run_date][[*KEYS, "forecast_qty"]]

    products = pd.read_csv(RAW / "product_snapshot_2025_07.csv", parse_dates=["phaseout_date"])
    phaseout = products.set_index("product_code")["phaseout_date"]
    ts = pd.read_csv(RAW / "forecast.csv", parse_dates=["version_month", "target_month"])
    ts = ts[ts["version_month"] == ts["version_month"].max()].merge(products[["product_code", "product_group"]])
    planner_latest = ts.groupby([*KEYS, "product_code"], as_index=False)["forecast_qty"].sum()
    sales = load_sales()

    by_sku, unallocated = sku_split(forecast, planner_latest, sales, run_date, phaseout)
    by_plant = plant_split(by_sku, sales, run_date)
    pir = to_pir(by_plant, pd.read_csv(MAP_DIR / "material_map.csv", dtype=str),
                 pd.read_csv(MAP_DIR / "plant_map.csv", dtype=str), args.version)
    pir.to_csv(args.out, index=False)

    print(f"Çalıştırma {run_date:%Y-%m}, versiyon {args.version}")
    print(f"  Model toplamı      {forecast['forecast_qty'].sum():>12,.1f}")
    print(f"  PIR toplamı        {pir['quantity'].sum():>12,}")
    stale = planner_latest["forecast_qty"].sum() - drop_phased_out(planner_latest, phaseout)["forecast_qty"].sum()
    if stale:
        print(f"  Uyarı: planlama TS'sinde satıştan kalkmış ürünlere {stale:,.0f} adet var; dağıtımda kullanılmadı")
    print(f"  Dağıtım dayanağı   {by_sku.groupby('split_basis')['forecast_qty'].sum().round(1).to_dict()}")
    if len(unallocated):
        print(f"  Dağıtılamadı       {unallocated['forecast_qty'].sum():,.1f} adet "
              f"({unallocated[['product_group', 'channel_code']].drop_duplicates().shape[0]} seri, geçmiş satış yok)")
    print(f"  {len(pir):,} satır, {pir['material'].nunique()} malzeme, {pir['plant'].nunique()} üretim yeri -> {args.out}")


if __name__ == "__main__":
    main()
