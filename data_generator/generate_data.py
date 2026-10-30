from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp("2024-01-01")
END = pd.Timestamp("2026-09-30")
SNAPSHOT_CHANGE = pd.Timestamp("2025-07-01")


PRODUCT_GROUPS = [
    ("Ankastre Fırın",        "Pişirici",   22, 1.6, (14000, 32000), "Üretim"),
    ("Set Üstü Ocak",         "Pişirici",   18, 1.4, (6000, 18000),  "Üretim"),
    ("Solo Fırın",            "Pişirici",   10, 1.1, (9000, 16000),  "Üretim"),
    ("Davlumbaz",             "Pişirici",   14, 1.2, (5000, 15000),  "Satınalma"),
    ("Mikrodalga",            "Pişirici",    8, 0.9, (4000, 9000),   "Satınalma"),
    ("Elektrikli Termosifon", "Termosifon", 12, 1.5, (5500, 11000),  "Üretim"),
    ("Anında Isıtıcı",        "Termosifon",  6, 0.6, (2500, 6000),   "Satınalma"),
]
GROUP_CODE = {
    "Ankastre Fırın": "AF", "Set Üstü Ocak": "SO", "Solo Fırın": "SF", "Davlumbaz": "DV",
    "Mikrodalga": "MD", "Elektrikli Termosifon": "ET", "Anında Isıtıcı": "AI",
}
BRANDS = ["Anka", "Lumo", "Teras"]


GROUP_SEASONALITY = {
    "Pişirici":   [0.85, 0.85, 0.95, 1.00, 1.10, 1.15, 1.05, 1.00, 1.05, 1.00, 1.10, 0.90],
    "Termosifon": [1.35, 1.10, 0.85, 0.70, 0.60, 0.60, 0.65, 0.75, 0.95, 1.25, 1.45, 1.55],
}


CHANNELS = [
    ("BAY", "Bayi",          "Toptan",    1.00,  0.03, None),
    ("MAG", "Mağazacılık",   "Perakende", 0.55, -0.08, None),
    ("ETC", "E-Ticaret",     "Online",    0.45,  0.25, {11: 1.8, 12: 1.2}),
    ("CYZ", "Çeyiz",         "Perakende", 0.30,  0.02, {5: 1.4, 6: 1.6, 7: 1.5, 8: 1.4, 9: 1.3, 1: 0.6, 2: 0.6}),
    ("ZNC", "Zincir",        "Toptan",    0.40,  0.05, None),
    ("DST", "Distribütör",   "Toptan",    0.25,  0.00, None),
    ("OUT", "Outlet",        "Perakende", 0.15,  0.04, None),
]
WAREHOUSES = [
    ("MNS", "Manisa Merkez Depo", "Manisa",   "Ege"),
    ("IST", "İstanbul Bölge Depo", "İstanbul", "Marmara"),
    ("ANK", "Ankara Bölge Depo",  "Ankara",   "İç Anadolu"),
    ("ADN", "Adana Bölge Depo",   "Adana",    "Akdeniz"),
]
WAREHOUSE_SHARE = [0.40, 0.30, 0.18, 0.12]


SUPPLIERS = [
    ("SUP01", "Delta Havalandırma San. A.Ş.", "Türkiye", 21, 0.93, 0.95),
    ("SUP02", "Marmara Elektronik Ltd.",      "Türkiye", 28, 0.88, 0.92),
    ("SUP03", "Orient Appliance Co.",         "Çin",     60, 0.70, 0.85),
    ("SUP04", "Hydra Isı Sistemleri A.Ş.",    "Türkiye", 25, 0.90, 0.94),
    ("SUP05", "EuroKitchen GmbH",             "Almanya", 35, 0.95, 0.97),
]
SUPPLIER_BY_GROUP = {
    "Davlumbaz": ["SUP01", "SUP05"],
    "Mikrodalga": ["SUP03", "SUP02"],
    "Anında Isıtıcı": ["SUP04", "SUP03"],
}

WEEKDAY_FACTOR = np.array([1.15, 1.10, 1.05, 1.05, 1.10, 0.55, 0.0])


def month_starts(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="MS")


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    family_no = 1
    for group, category, n, base, (pmin, pmax), sourcing in PRODUCT_GROUPS:
        code = GROUP_CODE[group]
        i = 0
        while i < n:

            is_family = rng.random() < 0.45 and i + 1 < n
            brand = rng.choice(BRANDS, p=[0.6, 0.25, 0.15])
            price = round(float(rng.uniform(pmin, pmax)), -1)
            muadil = f"M{family_no:04d}" if is_family else None
            if is_family:
                switch = START + pd.DateOffset(months=int(rng.integers(8, 26)))
                rows.append(dict(product_code=f"{code}{10000 + i}", group=group, category=category,
                                 brand=brand, muadil_id=muadil, list_price=price, base=base,
                                 launch_date=START - pd.DateOffset(months=int(rng.integers(6, 30))),
                                 phaseout_date=switch + pd.DateOffset(months=2), sourcing_type=sourcing))
                rows.append(dict(product_code=f"{code}{10000 + i + 1}", group=group, category=category,
                                 brand=brand, muadil_id=muadil, list_price=round(price * 1.08, -1), base=base,
                                 launch_date=switch, phaseout_date=None, sourcing_type=sourcing))
                i += 2
                family_no += 1
            else:
                launch = START - pd.DateOffset(months=int(rng.integers(3, 30)))
                if rng.random() < 0.15:
                    launch = START + pd.DateOffset(months=int(rng.integers(3, 28)))
                rows.append(dict(product_code=f"{code}{10000 + i}", group=group, category=category,
                                 brand=brand, muadil_id=muadil, list_price=price, base=base,
                                 launch_date=launch, phaseout_date=None, sourcing_type=sourcing))
                i += 1
    df = pd.DataFrame(rows)
    df["base"] = df["base"] * rng.lognormal(0, 0.45, len(df))
    df["product_name"] = df.apply(
        lambda r: f"{r.brand} {r.group} {r.product_code[-3:]}", axis=1)
    return df


def lifecycle_status(row, as_of: pd.Timestamp) -> str:
    if row.launch_date > as_of:
        return "Planlandı"
    if pd.notna(row.phaseout_date) and row.phaseout_date <= as_of:
        return "Pasif"
    if pd.notna(row.phaseout_date) and row.phaseout_date - as_of <= pd.Timedelta(days=120):
        return "Çıkışta"
    if as_of - row.launch_date <= pd.Timedelta(days=180):
        return "Yeni"
    return "Aktif"


def product_snapshot(products: pd.DataFrame, as_of: pd.Timestamp, price_factor: pd.Series) -> pd.DataFrame:
    snap = products.copy()
    snap["lifecycle_status"] = snap.apply(lambda r: lifecycle_status(r, as_of), axis=1)
    snap["list_price"] = (snap["list_price"] * price_factor).round(-1)
    out = snap[["product_code", "product_name", "group", "category", "brand", "muadil_id",
                "lifecycle_status", "list_price", "launch_date", "phaseout_date", "sourcing_type"]]
    out = out.rename(columns={"group": "product_group"})
    for c in ("launch_date", "phaseout_date"):
        out[c] = pd.to_datetime(out[c]).dt.strftime("%Y-%m-%d")
    return out


def build_sales(rng: np.random.Generator, products: pd.DataFrame, price_2025h2: pd.Series) -> pd.DataFrame:
    days = pd.date_range(START, END, freq="D")
    month_idx = days.month.values - 1
    years_from_start = ((days - START).days.values / 365.25)
    wd = WEEKDAY_FACTOR[days.weekday.values]

    inflation = (1 + 0.025) ** ((days.year.values - 2024) * 12 + days.month.values - 1)

    frames = []
    for _, p in products.iterrows():
        n_ch = int(rng.integers(4, 7))
        weights = np.array([c[3] for c in CHANNELS])
        chosen = rng.choice(len(CHANNELS), size=n_ch, replace=False, p=weights / weights.sum())
        if 0 not in chosen:
            chosen[0] = 0
        season = np.array(GROUP_SEASONALITY[p.category])[month_idx]


        life = np.ones(len(days))
        launch = pd.Timestamp(p.launch_date)
        life[days < launch] = 0.0
        ramp = (days >= launch) & (days < launch + pd.Timedelta(days=90))
        life[ramp] = ((days[ramp] - launch).days.values + 1) / 90
        if pd.notna(p.phaseout_date):
            po = pd.Timestamp(p.phaseout_date)
            fade = (days >= po - pd.Timedelta(days=60)) & (days < po)
            life[fade] = (po - days[fade]).days.values / 60
            life[days >= po] = 0.0

        for ci in np.unique(chosen):
            code, _, _, w, trend, extra = CHANNELS[ci]
            ch_season = np.ones(len(days))
            if extra:
                for m, f in extra.items():
                    ch_season[days.month.values == m] = f
            lam = p.base * w * season * ch_season * (1 + trend) ** years_from_start * wd * life
            lam *= rng.lognormal(0, 0.15, len(days))
            qty = rng.poisson(lam)
            mask = qty > 0
            if not mask.any():
                continue
            d = days[mask]
            price_base = np.where(d < SNAPSHOT_CHANGE, p.list_price, price_2025h2[p.name])
            discount = {"BAY": 0.78, "ZNC": 0.75, "DST": 0.72, "MAG": 0.92,
                        "ETC": 0.88, "CYZ": 0.85, "OUT": 0.65}[code]
            unit_price = price_base * discount * inflation[mask] / inflation[0] * \
                rng.uniform(0.97, 1.03, mask.sum())
            frames.append(pd.DataFrame({
                "invoice_date": d,
                "product_code": p.product_code,
                "channel_code": code,
                "qty": qty[mask],
                "net_amount": np.round(qty[mask] * unit_price, 2),
            }))
    sales = pd.concat(frames, ignore_index=True)
    sales["warehouse_code"] = rng.choice([w[0] for w in WAREHOUSES], size=len(sales), p=WAREHOUSE_SHARE)
    sales = sales.sort_values(["invoice_date", "channel_code", "product_code"]).reset_index(drop=True)
    sales["invoice_no"] = ["F" + d.strftime("%y%m") + f"{i:07d}"
                           for i, d in enumerate(sales["invoice_date"])]


    n = len(sales)
    returns = sales.sample(n=int(n * 0.004), random_state=1).copy()
    returns["invoice_date"] = returns["invoice_date"] + pd.to_timedelta(rng.integers(5, 25, len(returns)), unit="D")
    returns = returns[returns["invoice_date"] <= END]
    returns["qty"] = -np.maximum(1, (returns["qty"] * 0.5).astype(int))
    returns["net_amount"] = np.round(-returns["net_amount"].abs() * 0.5, 2)
    returns["invoice_no"] = "I" + returns["invoice_no"].str[1:]
    dups = sales.sample(n=int(n * 0.002), random_state=2)
    unknown = sales.sample(n=40, random_state=3).copy()
    unknown["channel_code"] = "XX99"
    unknown["invoice_no"] = "U" + unknown["invoice_no"].str[1:]
    sales = pd.concat([sales, returns, dups, unknown], ignore_index=True)
    sales["invoice_date"] = pd.to_datetime(sales["invoice_date"]).dt.strftime("%Y-%m-%d")
    return sales[["invoice_no", "invoice_date", "product_code", "channel_code", "warehouse_code", "qty", "net_amount"]]


def monthly_actuals(sales: pd.DataFrame) -> pd.DataFrame:
    s = sales[sales["channel_code"] != "XX99"].drop_duplicates()
    s = s.assign(month=pd.to_datetime(s["invoice_date"]).dt.to_period("M").dt.to_timestamp())
    return s.groupby(["month", "product_code", "channel_code"], as_index=False)["qty"].sum()


def build_forecast(rng: np.random.Generator, actual_m: pd.DataFrame) -> pd.DataFrame:
    piv = actual_m.pivot_table(index=["product_code", "channel_code"], columns="month",
                               values="qty", aggfunc="sum", fill_value=0)
    months = list(piv.columns)
    future = list(month_starts(END + pd.Timedelta(days=1), END + pd.DateOffset(months=5)))
    all_targets = months + future
    out = []

    for vi, v in enumerate(month_starts(START + pd.DateOffset(months=3), END + pd.DateOffset(months=1))):
        for lag in range(5):
            t = v + pd.DateOffset(months=lag)
            if t not in all_targets:
                continue
            if t in piv.columns:
                truth = piv[t].values.astype(float)
            else:
                truth = piv[months[-3:]].mean(axis=1).values

            err = rng.normal(0.06, 0.12 + 0.05 * lag, len(truth))
            fc = np.maximum(0, np.round(truth * (1 + err) + rng.normal(0, 1.5, len(truth))))
            out.append(pd.DataFrame({
                "version_month": v.strftime("%Y-%m-%d"),
                "target_month": t.strftime("%Y-%m-%d"),
                "product_code": piv.index.get_level_values(0),
                "channel_code": piv.index.get_level_values(1),
                "forecast_qty": fc.astype(int),
            }))
    fc = pd.concat(out, ignore_index=True)
    return fc[fc["forecast_qty"] > 0]


def build_budget(rng: np.random.Generator, actual_m: pd.DataFrame, products: pd.DataFrame,
                 sales: pd.DataFrame) -> pd.DataFrame:
    grp = products.set_index("product_code")["group"]
    a = actual_m.assign(product_group=actual_m["product_code"].map(grp))
    s = sales[sales["channel_code"] != "XX99"].drop_duplicates()
    s = s.assign(month=pd.to_datetime(s["invoice_date"]).dt.to_period("M").dt.to_timestamp(),
                 product_group=s["product_code"].map(grp))
    amt = s.groupby(["month", "product_group", "channel_code"])["net_amount"].sum()
    q = a.groupby(["month", "product_group", "channel_code"])["qty"].sum()
    base = pd.concat([q, amt], axis=1).reset_index()
    base["avg_price"] = base["net_amount"] / base["qty"].replace(0, np.nan)
    out = []
    for year in (2024, 2025, 2026, 2027):
        for m in range(1, 13):
            month = pd.Timestamp(year=year, month=m, day=1)
            ref = month - pd.DateOffset(years=1)
            while ref not in set(base["month"]) and ref > START:
                ref -= pd.DateOffset(years=1)
            if ref < START:
                ref = pd.Timestamp(year=2024, month=m, day=1)
            r = base[base["month"] == ref]
            if r.empty:
                continue
            growth = rng.normal(1.08, 0.05, len(r))
            infl = 1.30 if year > 2024 else 1.0
            bq = np.round(r["qty"].values * growth).astype(int)
            out.append(pd.DataFrame({
                "budget_year": year,
                "budget_month": month.strftime("%Y-%m-%d"),
                "product_group": r["product_group"].values,
                "channel_code": r["channel_code"].values,
                "budget_qty": bq,
                "budget_amount": np.round(bq * r["avg_price"].fillna(0).values * infl, 2),
            }))
    return pd.concat(out, ignore_index=True)


def build_inventory(rng: np.random.Generator, actual_m: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    prod_month = actual_m.groupby(["month", "product_code"])["qty"].sum().unstack(fill_value=0)
    out = []
    phase = products.set_index("product_code")["phaseout_date"]
    for month in prod_month.index:
        snap = month + pd.offsets.MonthEnd(0)
        nxt = prod_month.loc[month]

        cover = rng.gamma(4, 0.38, len(nxt))
        on_hand = np.round(nxt.values * cover).astype(int)
        po = pd.to_datetime(phase.reindex(nxt.index))
        aging_ratio = np.where(po.notna() & (po <= snap + pd.Timedelta(days=90)), 0.45, 0.08)
        for wi, (wcode, *_rest) in enumerate(WAREHOUSES):
            wq = np.round(on_hand * WAREHOUSE_SHARE[wi] * rng.uniform(0.8, 1.2, len(on_hand))).astype(int)
            q90 = np.round(wq * aging_ratio * rng.uniform(0.5, 1.5, len(wq))).astype(int)
            q90 = np.minimum(q90, wq)
            rest = wq - q90
            split = rng.dirichlet([5, 3, 2], len(wq))
            q0 = np.floor(rest * split[:, 0]).astype(int)
            q31 = np.floor(rest * split[:, 1]).astype(int)
            q61 = rest - q0 - q31
            df = pd.DataFrame({
                "snapshot_date": snap.strftime("%Y-%m-%d"), "product_code": nxt.index,
                "warehouse_code": wcode, "on_hand_qty": wq,
                "qty_0_30": q0, "qty_31_60": q31, "qty_61_90": q61, "qty_90_plus": q90})
            out.append(df[df["on_hand_qty"] > 0])
    return pd.concat(out, ignore_index=True)


def build_purchase_orders(rng: np.random.Generator, actual_m: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    sup = {s[0]: s for s in SUPPLIERS}
    bought = products[products["sourcing_type"] == "Satınalma"]
    monthly = actual_m.groupby(["month", "product_code"])["qty"].sum()
    rows = []
    po_no = 450000
    for week in pd.date_range(START, END, freq="W-MON"):
        for _, p in bought.iterrows():
            if rng.random() < 0.55:
                continue
            m = week.to_period("M").to_timestamp()
            base = monthly.get((m, p.product_code), 0)
            if base <= 0:
                continue
            scode = rng.choice(SUPPLIER_BY_GROUP[p.group])
            _, _, country, lead, p_on_time, p_full = sup[scode]
            ordered = int(max(10, round(base / 2.2 * rng.uniform(0.7, 1.3), -1)))
            promised = week + pd.Timedelta(days=lead)
            if promised > END + pd.Timedelta(days=60):
                continue

            crisis = country == "Çin" and pd.Timestamp("2025-07-01") <= week <= pd.Timestamp("2025-12-31")
            if rng.random() < (p_on_time - (0.25 if crisis else 0)):
                delay = int(rng.integers(-1, 2))
            else:
                delay = int(rng.integers(2, 30 if crisis else 15))
            delivered = promised + pd.Timedelta(days=delay)
            delivered_qty = ordered if rng.random() < p_full else int(ordered * rng.uniform(0.6, 0.95))
            if delivered > END:
                delivered, delivered_qty = None, 0
            po_no += 1
            rows.append({
                "po_no": f"PO{po_no}", "po_line": 10, "supplier_code": scode,
                "product_code": p.product_code, "order_date": week.strftime("%Y-%m-%d"),
                "promised_date": promised.strftime("%Y-%m-%d"),
                "delivered_date": delivered.strftime("%Y-%m-%d") if delivered is not None else None,
                "ordered_qty": ordered, "delivered_qty": delivered_qty})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "raw"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    products = build_products(rng)
    no_change = pd.Series(1.0, index=products.index)
    price_up = pd.Series(np.where(rng.random(len(products)) < 0.6, 1.35, 1.0), index=products.index)

    snap1 = product_snapshot(products, SNAPSHOT_CHANGE - pd.Timedelta(days=1), no_change)
    snap2 = product_snapshot(products, END, price_up)

    sales = build_sales(rng, products, products["list_price"] * price_up)
    actual_m = monthly_actuals(sales)

    files = {
        "product_snapshot_2024_01.csv": snap1,
        "product_snapshot_2025_07.csv": snap2,
        "channel.csv": pd.DataFrame([c[:3] for c in CHANNELS], columns=["channel_code", "channel_name", "channel_type"]),
        "warehouse.csv": pd.DataFrame(WAREHOUSES, columns=["warehouse_code", "warehouse_name", "city", "region"]),
        "supplier.csv": pd.DataFrame([s[:4] for s in SUPPLIERS],
                                     columns=["supplier_code", "supplier_name", "country", "std_lead_time_days"]),
        "sales.csv": sales,
        "forecast.csv": build_forecast(rng, actual_m),
        "budget.csv": build_budget(rng, actual_m, products, sales),
        "inventory.csv": build_inventory(rng, actual_m, products),
        "purchase_order.csv": build_purchase_orders(rng, actual_m, products),
    }
    for name, df in files.items():
        df.to_csv(out / name, index=False, encoding="utf-8")
        print(f"{name:32s} {len(df):>9,} satır")


if __name__ == "__main__":
    main()
