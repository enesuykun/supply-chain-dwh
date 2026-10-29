USE SupplyChainDW;
GO
SET STATISTICS IO, TIME ON;
GO

-- 1. baz olcum (heap)
SELECT d.year_month, p.product_group, c.channel_name, SUM(f.qty) AS qty, SUM(f.net_amount) AS amount
FROM dw.fact_sales f
JOIN dw.dim_date d    ON d.date_key = f.date_key
JOIN dw.dim_product p ON p.product_key = f.product_key
JOIN dw.dim_channel c ON c.channel_key = f.channel_key
WHERE d.[year] = 2025
GROUP BY d.year_month, p.product_group, c.channel_name;
GO

-- 2. sargable olmayan filtre
SELECT SUM(f.qty)
FROM dw.fact_sales f
WHERE YEAR(CONVERT(DATE, CONVERT(CHAR(8), f.date_key), 112)) = 2025;

-- 2. sargable
SELECT SUM(f.qty)
FROM dw.fact_sales f
WHERE f.date_key BETWEEN 20250101 AND 20251231;
GO

-- 3. clustered columnstore
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dw.fact_sales') AND name = N'cci_fact_sales')
BEGIN
    CREATE CLUSTERED INDEX cci_fact_sales ON dw.fact_sales (date_key);
    CREATE CLUSTERED COLUMNSTORE INDEX cci_fact_sales ON dw.fact_sales
        WITH (DROP_EXISTING = ON, MAXDOP = 1);
END;
GO

-- 3. tekrar olcum
SELECT d.year_month, p.product_group, c.channel_name, SUM(f.qty) AS qty, SUM(f.net_amount) AS amount
FROM dw.fact_sales f
JOIN dw.dim_date d    ON d.date_key = f.date_key
JOIN dw.dim_product p ON p.product_key = f.product_key
JOIN dw.dim_channel c ON c.channel_key = f.channel_key
WHERE f.date_key BETWEEN 20250101 AND 20251231
GROUP BY d.year_month, p.product_group, c.channel_name;
GO

SELECT rg.row_group_id, rg.state_desc, rg.total_rows, rg.deleted_rows, rg.size_in_bytes
FROM sys.dm_db_column_store_row_group_physical_stats rg
WHERE rg.object_id = OBJECT_ID(N'dw.fact_sales');
GO

-- 4. covering index oncesi
SELECT po_no, product_key, promised_date_key, ordered_qty
FROM dw.fact_purchase_order
WHERE supplier_key = 3 AND delivered_date_key IS NULL;
GO

-- 4. covering index
CREATE NONCLUSTERED INDEX ix_po_supplier_open
    ON dw.fact_purchase_order (supplier_key, delivered_date_key)
    INCLUDE (product_key, promised_date_key, ordered_qty);
GO

SELECT po_no, product_key, promised_date_key, ordered_qty
FROM dw.fact_purchase_order
WHERE supplier_key = 3 AND delivered_date_key IS NULL;
GO

-- 5. lag index
CREATE NONCLUSTERED INDEX ix_fact_forecast_lag
    ON dw.fact_forecast (lag_month, target_date_key)
    INCLUDE (product_key, channel_key, forecast_qty);
GO

-- 6. correlated subquery vs window function
SELECT i.product_key, i.date_key, i.on_hand_qty
FROM dw.fact_inventory_snapshot i
WHERE i.date_key = (SELECT MAX(x.date_key) FROM dw.fact_inventory_snapshot x WHERE x.product_key = i.product_key);

SELECT product_key, date_key, on_hand_qty
FROM (
    SELECT product_key, date_key, SUM(on_hand_qty) AS on_hand_qty,
           ROW_NUMBER() OVER (PARTITION BY product_key ORDER BY date_key DESC) AS rn
    FROM dw.fact_inventory_snapshot
    GROUP BY product_key, date_key
) t
WHERE rn = 1;
GO

-- 7. istatistik ve query store
UPDATE STATISTICS dw.fact_sales WITH FULLSCAN;
UPDATE STATISTICS dw.fact_forecast WITH FULLSCAN;
GO

SELECT TOP (10)
       qt.query_sql_text,
       rs.count_executions,
       CAST(rs.avg_duration / 1000.0 AS DECIMAL(12,2))     AS avg_duration_ms,
       CAST(rs.avg_logical_io_reads AS DECIMAL(14,0))       AS avg_logical_reads
FROM sys.query_store_query_text qt
JOIN sys.query_store_query q          ON q.query_text_id = qt.query_text_id
JOIN sys.query_store_plan p           ON p.query_id = q.query_id
JOIN sys.query_store_runtime_stats rs ON rs.plan_id = p.plan_id
ORDER BY rs.avg_logical_io_reads DESC;
GO

SET STATISTICS IO, TIME OFF;
GO
