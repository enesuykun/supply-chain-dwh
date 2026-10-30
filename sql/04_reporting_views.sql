USE SupplyChainDW;
GO

CREATE OR ALTER VIEW rpt.v_sales_monthly
AS
SELECT d.month_start,
       p.product_group,
       p.category,
       c.channel_name,
       c.channel_type,
       SUM(f.qty)                                              AS net_qty,
       SUM(CASE WHEN f.is_return = 0 THEN f.qty ELSE 0 END)    AS gross_qty,
       SUM(CASE WHEN f.is_return = 1 THEN -f.qty ELSE 0 END)   AS return_qty,
       SUM(f.net_amount)                                       AS net_amount
FROM dw.fact_sales f
JOIN dw.dim_date d    ON d.date_key = f.date_key
JOIN dw.dim_product p ON p.product_key = f.product_key
JOIN dw.dim_channel c ON c.channel_key = f.channel_key
GROUP BY d.month_start, p.product_group, p.category, c.channel_name, c.channel_type;
GO

CREATE OR ALTER VIEW rpt.v_forecast_vs_actual
AS
WITH act AS (
    SELECT d.month_start, p.product_code, f.channel_key, SUM(f.qty) AS actual_qty
    FROM dw.fact_sales f
    JOIN dw.dim_date d    ON d.date_key = f.date_key
    JOIN dw.dim_product p ON p.product_key = f.product_key
    GROUP BY d.month_start, p.product_code, f.channel_key
), fc AS (
    SELECT d.month_start, p.product_code, f.channel_key, f.lag_month, SUM(f.forecast_qty) AS forecast_qty
    FROM dw.fact_forecast f
    JOIN dw.dim_date d    ON d.date_key = f.target_date_key
    JOIN dw.dim_product p ON p.product_key = f.product_key
    GROUP BY d.month_start, p.product_code, f.channel_key, f.lag_month
), act_lag AS (
    SELECT a.month_start, a.product_code, a.channel_key, l.lag_month, a.actual_qty
    FROM act a
    CROSS JOIN (VALUES (0), (1), (2), (3), (4)) AS l(lag_month)
    WHERE EXISTS (SELECT 1 FROM fc x WHERE x.month_start = a.month_start AND x.lag_month = l.lag_month)
), closed AS (
    SELECT MAX(month_start) AS last_closed_month FROM act
)
SELECT COALESCE(fc.month_start, a.month_start)   AS month_start,
       COALESCE(fc.product_code, a.product_code) AS product_code,
       COALESCE(fc.channel_key, a.channel_key)   AS channel_key,
       COALESCE(fc.lag_month, a.lag_month)       AS lag_month,
       ISNULL(fc.forecast_qty, 0)                AS forecast_qty,
       ISNULL(a.actual_qty, 0)                   AS actual_qty,
       ISNULL(fc.forecast_qty, 0) - ISNULL(a.actual_qty, 0)      AS error_qty,
       ABS(ISNULL(fc.forecast_qty, 0) - ISNULL(a.actual_qty, 0)) AS abs_error_qty
FROM fc
FULL OUTER JOIN act_lag a
       ON a.month_start = fc.month_start AND a.product_code = fc.product_code
      AND a.channel_key = fc.channel_key AND a.lag_month = fc.lag_month
CROSS JOIN closed
WHERE COALESCE(fc.month_start, a.month_start) <= closed.last_closed_month;
GO

CREATE OR ALTER VIEW rpt.v_forecast_accuracy
AS
SELECT v.month_start,
       p.product_group,
       p.category,
       c.channel_name,
       v.lag_month,
       SUM(v.forecast_qty)  AS forecast_qty,
       SUM(v.actual_qty)    AS actual_qty,
       SUM(v.abs_error_qty) AS abs_error_qty,
       CAST(1 - SUM(v.abs_error_qty) * 1.0 / NULLIF(SUM(v.actual_qty), 0) AS DECIMAL(9,4)) AS forecast_accuracy,
       CAST(SUM(v.error_qty) * 1.0 / NULLIF(SUM(v.actual_qty), 0) AS DECIMAL(9,4))         AS forecast_bias
FROM rpt.v_forecast_vs_actual v
JOIN dw.dim_product p ON p.product_code = v.product_code AND p.is_current = 1
JOIN dw.dim_channel c ON c.channel_key = v.channel_key
GROUP BY v.month_start, p.product_group, p.category, c.channel_name, v.lag_month;
GO

CREATE OR ALTER VIEW rpt.v_budget_ts_actual
AS
WITH u AS (
    SELECT d.month_start, b.product_group_key, b.channel_key,
           b.budget_qty, 0 AS ts_qty, 0 AS actual_qty, b.budget_amount, CAST(0 AS DECIMAL(16,2)) AS actual_amount
    FROM dw.fact_budget b
    JOIN dw.dim_date d ON d.date_key = b.date_key
    UNION ALL
    SELECT d.month_start, p.product_group_key, f.channel_key,
           0, f.forecast_qty, 0, 0, 0
    FROM dw.fact_forecast f
    JOIN dw.dim_date d    ON d.date_key = f.target_date_key
    JOIN dw.dim_product p ON p.product_key = f.product_key
    WHERE f.lag_month = 1
    UNION ALL
    SELECT d.month_start, p.product_group_key, f.channel_key,
           0, 0, f.qty, 0, f.net_amount
    FROM dw.fact_sales f
    JOIN dw.dim_date d    ON d.date_key = f.date_key
    JOIN dw.dim_product p ON p.product_key = f.product_key
)
SELECT u.month_start,
       g.product_group,
       g.category,
       c.channel_name,
       SUM(u.budget_qty)     AS budget_qty,
       SUM(u.ts_qty)         AS ts_qty,
       SUM(u.actual_qty)     AS actual_qty,
       SUM(u.budget_amount)  AS budget_amount,
       SUM(u.actual_amount)  AS actual_amount,
       CAST(SUM(u.actual_qty) * 1.0 / NULLIF(SUM(u.budget_qty), 0) AS DECIMAL(9,4)) AS budget_achievement,
       CAST(SUM(u.ts_qty)     * 1.0 / NULLIF(SUM(u.budget_qty), 0) AS DECIMAL(9,4)) AS ts_to_budget
FROM u
JOIN dw.dim_product_group g ON g.product_group_key = u.product_group_key
JOIN dw.dim_channel c       ON c.channel_key = u.channel_key
GROUP BY u.month_start, g.product_group, g.category, c.channel_name;
GO

CREATE OR ALTER VIEW rpt.v_stock_cover
AS
WITH months AS (
    SELECT DISTINCT month_start FROM dw.dim_date
    WHERE date_key IN (SELECT date_key FROM dw.fact_inventory_snapshot)
), products AS (
    SELECT product_code, product_group, category, lifecycle_status
    FROM dw.dim_product WHERE is_current = 1 AND product_key <> -1
), sales AS (
    SELECT d.month_start, p.product_code, SUM(f.qty) AS qty
    FROM dw.fact_sales f
    JOIN dw.dim_date d    ON d.date_key = f.date_key
    JOIN dw.dim_product p ON p.product_key = f.product_key
    GROUP BY d.month_start, p.product_code
), grid AS (
    SELECT m.month_start, pr.product_code, ISNULL(s.qty, 0) AS qty
    FROM months m
    CROSS JOIN products pr
    LEFT JOIN sales s ON s.month_start = m.month_start AND s.product_code = pr.product_code
), avg3 AS (
    SELECT month_start, product_code,
           AVG(CAST(qty AS DECIMAL(12,2))) OVER (PARTITION BY product_code ORDER BY month_start
                                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS avg_sales_3m
    FROM grid
), inv AS (
    SELECT d.month_start, p.product_code,
           SUM(i.on_hand_qty) AS on_hand_qty, SUM(i.qty_90_plus) AS qty_90_plus
    FROM dw.fact_inventory_snapshot i
    JOIN dw.dim_date d    ON d.date_key = i.date_key
    JOIN dw.dim_product p ON p.product_key = i.product_key
    GROUP BY d.month_start, p.product_code
)
SELECT inv.month_start,
       inv.product_code,
       pr.product_group,
       pr.category,
       pr.lifecycle_status,
       inv.on_hand_qty,
       inv.qty_90_plus,
       a.avg_sales_3m,
       CAST(inv.on_hand_qty / NULLIF(a.avg_sales_3m, 0) AS DECIMAL(9,2)) AS stock_months,
       CASE WHEN ISNULL(a.avg_sales_3m, 0) = 0             THEN N'Satışsız stok'
            WHEN inv.on_hand_qty / a.avg_sales_3m < 0.5    THEN N'Kritik (<0,5 ay)'
            WHEN inv.on_hand_qty / a.avg_sales_3m > 3      THEN N'Fazla (>3 ay)'
            ELSE N'Normal' END AS stock_status
FROM inv
JOIN products pr ON pr.product_code = inv.product_code
LEFT JOIN avg3 a ON a.product_code = inv.product_code AND a.month_start = inv.month_start;
GO

CREATE OR ALTER VIEW rpt.v_inventory_aging
AS
SELECT d.month_start,
       p.product_group,
       w.warehouse_name,
       SUM(i.on_hand_qty) AS on_hand_qty,
       SUM(i.qty_0_30)    AS qty_0_30,
       SUM(i.qty_31_60)   AS qty_31_60,
       SUM(i.qty_61_90)   AS qty_61_90,
       SUM(i.qty_90_plus) AS qty_90_plus,
       CAST(SUM(i.qty_90_plus) * 1.0 / NULLIF(SUM(i.on_hand_qty), 0) AS DECIMAL(9,4)) AS share_90_plus
FROM dw.fact_inventory_snapshot i
JOIN dw.dim_date d      ON d.date_key = i.date_key
JOIN dw.dim_product p   ON p.product_key = i.product_key
JOIN dw.dim_warehouse w ON w.warehouse_key = i.warehouse_key
GROUP BY d.month_start, p.product_group, w.warehouse_name;
GO

CREATE OR ALTER VIEW rpt.v_supplier_otif
AS
SELECT d.month_start              AS delivery_month,
       s.supplier_name,
       s.country,
       s.is_import,
       COUNT(*)                   AS delivered_lines,
       AVG(CAST(f.is_on_time AS DECIMAL(5,4))) AS on_time_rate,
       AVG(CAST(f.is_in_full AS DECIMAL(5,4))) AS in_full_rate,
       AVG(CAST(f.is_otif    AS DECIMAL(5,4))) AS otif_rate,
       AVG(CAST(f.delay_days AS DECIMAL(9,2))) AS avg_delay_days,
       SUM(f.ordered_qty)         AS ordered_qty,
       SUM(f.delivered_qty)       AS delivered_qty
FROM dw.fact_purchase_order f
JOIN dw.dim_date d     ON d.date_key = f.delivered_date_key
JOIN dw.dim_supplier s ON s.supplier_key = f.supplier_key
GROUP BY d.month_start, s.supplier_name, s.country, s.is_import;
GO

CREATE OR ALTER VIEW rpt.v_dq_summary
AS
SELECT l.load_id, l.proc_name, l.start_time, q.source_table, q.issue_type, COUNT(*) AS issue_count
FROM etl.dq_issue q
JOIN etl.load_log l ON l.load_id = q.load_id
GROUP BY l.load_id, l.proc_name, l.start_time, q.source_table, q.issue_type;
GO

CREATE OR ALTER VIEW rpt.v_ml_model_comparison
AS
WITH last_run AS (
    SELECT MAX(run_date_key) AS run_date_key FROM dw.fact_ml_backtest
)
SELECT d.full_date AS run_date,
       f.model_name,
       MIN(t.month_start) AS first_target_month,
       MAX(t.month_start) AS last_target_month,
       COUNT(DISTINCT CONCAT(f.product_group_key, N'|', f.channel_key)) AS series_count,
       SUM(f.forecast_qty)  AS forecast_qty,
       SUM(f.actual_qty)    AS actual_qty,
       CAST(1 - SUM(f.abs_error_qty) * 1.0 / NULLIF(SUM(f.actual_qty), 0) AS DECIMAL(9,4)) AS forecast_accuracy,
       CAST(SUM(f.error_qty) * 1.0 / NULLIF(SUM(f.actual_qty), 0) AS DECIMAL(9,4))         AS forecast_bias
FROM dw.fact_ml_backtest f
JOIN last_run r    ON r.run_date_key = f.run_date_key
JOIN dw.dim_date d ON d.date_key = f.run_date_key
JOIN dw.dim_date t ON t.date_key = f.target_date_key
GROUP BY d.full_date, f.model_name;
GO
