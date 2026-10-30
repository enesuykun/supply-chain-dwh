from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "output"
SQL_DIR = ROOT / "sql"
DB_NAME = "SupplyChainDW"
DDL_SCRIPTS = ["00_create_database.sql", "01_staging.sql", "02_dw_schema.sql",
               "03_etl_procedures.sql", "04_reporting_views.sql"]


DIMENSION_FILES = {
    "stg.channel": RAW / "channel.csv",
    "stg.warehouse": RAW / "warehouse.csv",
    "stg.supplier": RAW / "supplier.csv",
    "stg.product": RAW / "product_snapshot_2024_01.csv",
}
PRODUCT_SCD2_FILE = RAW / "product_snapshot_2025_07.csv"
FACT_FILES = {
    "stg.sales": RAW / "sales.csv",
    "stg.forecast": RAW / "forecast.csv",
    "stg.budget": RAW / "budget.csv",
    "stg.inventory": RAW / "inventory.csv",
    "stg.purchase_order": RAW / "purchase_order.csv",
    "stg.ml_forecast": OUTPUT / "ml_forecast.csv",
    "stg.ml_backtest": OUTPUT / "ml_backtest.csv",
}
CHUNK = 20_000


def load_env_file(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def split_batches(sql_text: str) -> list[str]:
    parts = re.split(r"^\s*GO\s*;?\s*$", sql_text, flags=re.IGNORECASE | re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    return df.replace({"": None})


def connect(database: str):
    import pyodbc

    if os.getenv("MSSQL_TRUSTED", "no").lower() == "yes":
        auth = "Trusted_Connection=yes;"
    else:
        auth = f"UID={os.getenv('MSSQL_USER', 'sa')};PWD={os.environ['MSSQL_PASSWORD']};"
    conn_str = (
        f"DRIVER={{{os.getenv('MSSQL_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
        f"SERVER={os.getenv('MSSQL_SERVER', 'localhost,1433')};"
        f"DATABASE={database};{auth}"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True)


def run_script(conn, path: Path) -> None:
    cur = conn.cursor()
    for batch in split_batches(path.read_text(encoding="utf-8")):
        cur.execute(batch)
        while cur.nextset():
            pass
    print(f"  ✓ {path.name}")


def load_table(conn, table: str, path: Path) -> int:
    df = read_csv(path)
    cur = conn.cursor()
    cur.execute(f"TRUNCATE TABLE {table};")
    cols = ", ".join(df.columns)
    marks = ", ".join("?" for _ in df.columns)
    cur.fast_executemany = True
    rows = df.itertuples(index=False, name=None)
    batch = []
    for r in rows:
        batch.append(r)
        if len(batch) == CHUNK:
            cur.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", batch)
            batch.clear()
    if batch:
        cur.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", batch)
    return len(df)


def exec_proc(conn, sql: str) -> None:
    t0 = time.perf_counter()
    cur = conn.cursor()
    cur.execute(sql)
    while cur.nextset():
        pass
    print(f"  ✓ {sql}  ({time.perf_counter() - t0:.1f} sn)")


def report(conn, first_load_id: int) -> None:
    cur = conn.cursor()
    print("\nYükleme logu (bu çalıştırma):")
    cur.execute("""
        SELECT proc_name, status, rows_inserted, rows_updated, rows_deleted
        FROM etl.load_log WHERE load_id > ? ORDER BY load_id""", first_load_id)
    for r in cur.fetchall():
        print(f"  {r.proc_name:38s} {r.status:8s} ins={r.rows_inserted}  upd={r.rows_updated}  del={r.rows_deleted}")
    print("\nVeri kalitesi bulguları:")
    cur.execute("""SELECT source_table, issue_type, COUNT(*) AS n FROM etl.dq_issue
                   WHERE load_id > ? GROUP BY source_table, issue_type""", first_load_id)
    for r in cur.fetchall():
        print(f"  {r.source_table:20s} {r.issue_type:18s} {r.n:>6,}")
    cur.execute("SELECT COUNT(*) FROM dw.dim_product WHERE is_current = 0")
    print(f"\nSCD2: kapatılmış (tarihçe) ürün versiyonu sayısı = {cur.fetchone()[0]}")


def dry_run() -> None:
    print("Dry run — veritabanına bağlanılmadı.\n")
    for name in DDL_SCRIPTS:
        n = len(split_batches((SQL_DIR / name).read_text(encoding="utf-8")))
        print(f"  {name:28s} {n:>3} batch")
    print()
    for table, path in {**DIMENSION_FILES, "stg.product (SCD2)": PRODUCT_SCD2_FILE, **FACT_FILES}.items():
        if path.exists():
            df = read_csv(path)
            print(f"  {table:22s} <- {path.name:30s} {len(df):>9,} satır, {df.shape[1]} kolon")
        else:
            print(f"  {table:22s} <- {path.name:30s} (dosya yok, atlanacak)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ddl", action="store_true", help="şema scriptlerini çalıştırma")
    ap.add_argument("--dry-run", action="store_true", help="bağlanmadan dosya kontrolü")
    args = ap.parse_args()
    load_env_file()

    if args.dry_run:
        dry_run()
        return

    t0 = time.perf_counter()
    if not args.skip_ddl:
        print("1) Şema kurulumu")
        with connect("master") as c:
            run_script(c, SQL_DIR / DDL_SCRIPTS[0])
        with connect(DB_NAME) as c:
            for name in DDL_SCRIPTS[1:]:
                run_script(c, SQL_DIR / name)

    with connect(DB_NAME) as c:
        first_load_id = c.cursor().execute("SELECT ISNULL(MAX(load_id), 0) FROM etl.load_log").fetchone()[0]
        print("2) Boyutlar (ilk snapshot)")
        for table, path in DIMENSION_FILES.items():
            print(f"  → {table:22s} {load_table(c, table, path):>9,} satır")
        exec_proc(c, "EXEC etl.usp_load_dimensions @effective_date = '2024-01-01';")

        print("3) Ürün master değişikliği (SCD Type 2)")
        print(f"  → stg.product            {load_table(c, 'stg.product', PRODUCT_SCD2_FILE):>9,} satır")
        exec_proc(c, "EXEC etl.usp_load_dim_product_group;")
        exec_proc(c, "EXEC etl.usp_load_dim_product @effective_date = '2025-07-01';")

        print("4) Olgular")
        for table, path in FACT_FILES.items():
            if path.exists():
                print(f"  → {table:22s} {load_table(c, table, path):>9,} satır")
            else:
                c.cursor().execute(f"TRUNCATE TABLE {table};")
                print(f"  → {table:22s} (dosya yok, atlandı)")
        exec_proc(c, "EXEC etl.usp_load_facts;")

        report(c, first_load_id)
    print(f"\nToplam süre: {time.perf_counter() - t0:.1f} sn")


if __name__ == "__main__":
    main()
