from pathlib import Path

import pytest
from run_pipeline import DDL_SCRIPTS, SQL_DIR, read_csv, split_batches


def test_split_batches_on_go_lines():
    sql = "CREATE TABLE a (x INT);\nGO\n  go ;\nSELECT 1;\nGO\n"
    assert split_batches(sql) == ["CREATE TABLE a (x INT);", "SELECT 1;"]


def test_split_batches_ignores_go_inside_identifiers():
    sql = "SELECT category FROM GOODS;\nGO"
    assert split_batches(sql) == ["SELECT category FROM GOODS;"]


@pytest.mark.parametrize("name", DDL_SCRIPTS)
def test_ddl_scripts_split_into_batches(name):
    batches = split_batches((SQL_DIR / name).read_text(encoding="utf-8"))
    assert batches
    assert not any(b.upper() == "GO" for b in batches)


def test_read_csv_maps_empty_to_none(tmp_path: Path):
    p = tmp_path / "t.csv"
    p.write_text("a,b\n01,\n", encoding="utf-8")
    df = read_csv(p)
    assert df.loc[0, "a"] == "01"  # baştaki sıfır korunur (dtype=str)
    assert df.loc[0, "b"] is None
