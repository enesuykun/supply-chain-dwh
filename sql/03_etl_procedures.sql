USE SupplyChainDW;
GO

CREATE OR ALTER PROCEDURE etl.usp_log_start
    @proc_name SYSNAME,
    @load_id   INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT etl.load_log (proc_name) VALUES (@proc_name);
    SET @load_id = SCOPE_IDENTITY();
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_log_end
    @load_id       INT,
    @rows_inserted INT = NULL,
    @rows_updated  INT = NULL,
    @rows_deleted  INT = NULL,
    @status        VARCHAR(10) = 'SUCCESS',
    @error_message NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE etl.load_log
       SET end_time      = SYSDATETIME(),
           rows_inserted = @rows_inserted,
           rows_updated  = @rows_updated,
           rows_deleted  = @rows_deleted,
           status        = @status,
           error_message = @error_message
     WHERE load_id = @load_id;
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_date
    @start_date DATE = '2023-01-01',
    @end_date   DATE = '2027-12-31'
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @load_id INT, @ins INT;
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_date', @load_id = @load_id OUTPUT;

    ;WITH n AS (
        SELECT TOP (DATEDIFF(DAY, @start_date, @end_date) + 1)
               ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS i
        FROM sys.all_objects a CROSS JOIN sys.all_objects b
    ), d AS (
        SELECT DATEADD(DAY, i, @start_date) AS dt,
               DATEDIFF(DAY, '19000101', DATEADD(DAY, i, @start_date)) % 7 AS dow0
        FROM n
    )
    INSERT dw.dim_date (date_key, full_date, [year], [quarter], [month], month_name_tr, year_month,
                        month_start, month_end, days_in_month, iso_week, day_of_week, day_name_tr,
                        is_weekend, is_month_start)
    SELECT CONVERT(INT, CONVERT(CHAR(8), dt, 112)),
           dt,
           YEAR(dt),
           DATEPART(QUARTER, dt),
           MONTH(dt),
           CHOOSE(MONTH(dt), N'Ocak', N'Şubat', N'Mart', N'Nisan', N'Mayıs', N'Haziran',
                             N'Temmuz', N'Ağustos', N'Eylül', N'Ekim', N'Kasım', N'Aralık'),
           CONVERT(CHAR(7), dt, 126),
           DATEFROMPARTS(YEAR(dt), MONTH(dt), 1),
           EOMONTH(dt),
           DAY(EOMONTH(dt)),
           DATEPART(ISO_WEEK, dt),
           dow0 + 1,
           CHOOSE(dow0 + 1, N'Pazartesi', N'Salı', N'Çarşamba', N'Perşembe', N'Cuma', N'Cumartesi', N'Pazar'),
           CASE WHEN dow0 >= 5 THEN 1 ELSE 0 END,
           CASE WHEN DAY(dt) = 1 THEN 1 ELSE 0 END
    FROM d
    WHERE NOT EXISTS (SELECT 1 FROM dw.dim_date x WHERE x.full_date = d.dt);
    SET @ins = @@ROWCOUNT;

    EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins;
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_channel
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT, @upd INT, @err NVARCHAR(4000);
    DECLARE @chg TABLE (act NVARCHAR(10));
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_channel', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        MERGE dw.dim_channel AS t
        USING (SELECT DISTINCT channel_code, channel_name, channel_type FROM stg.channel) AS s
           ON t.channel_code = s.channel_code
        WHEN MATCHED AND (t.channel_name <> s.channel_name OR t.channel_type <> s.channel_type) THEN
            UPDATE SET t.channel_name = s.channel_name, t.channel_type = s.channel_type
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (channel_code, channel_name, channel_type) VALUES (s.channel_code, s.channel_name, s.channel_type)
        OUTPUT $action INTO @chg;
        COMMIT;
        SELECT @ins = COUNT(CASE WHEN act = N'INSERT' THEN 1 END),
               @upd = COUNT(CASE WHEN act = N'UPDATE' THEN 1 END) FROM @chg;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_updated = @upd;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_warehouse
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT, @upd INT, @err NVARCHAR(4000);
    DECLARE @chg TABLE (act NVARCHAR(10));
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_warehouse', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        MERGE dw.dim_warehouse AS t
        USING (SELECT DISTINCT warehouse_code, warehouse_name, city, region FROM stg.warehouse) AS s
           ON t.warehouse_code = s.warehouse_code
        WHEN MATCHED AND (t.warehouse_name <> s.warehouse_name OR t.city <> s.city OR t.region <> s.region) THEN
            UPDATE SET t.warehouse_name = s.warehouse_name, t.city = s.city, t.region = s.region
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (warehouse_code, warehouse_name, city, region)
            VALUES (s.warehouse_code, s.warehouse_name, s.city, s.region)
        OUTPUT $action INTO @chg;
        COMMIT;
        SELECT @ins = COUNT(CASE WHEN act = N'INSERT' THEN 1 END),
               @upd = COUNT(CASE WHEN act = N'UPDATE' THEN 1 END) FROM @chg;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_updated = @upd;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_supplier
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT, @upd INT, @err NVARCHAR(4000);
    DECLARE @chg TABLE (act NVARCHAR(10));
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_supplier', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        MERGE dw.dim_supplier AS t
        USING (SELECT DISTINCT supplier_code, supplier_name, country,
                      CONVERT(BIT, CASE WHEN country = N'Türkiye' THEN 0 ELSE 1 END) AS is_import,
                      ISNULL(std_lead_time_days, 0) AS std_lead_time_days
               FROM stg.supplier) AS s
           ON t.supplier_code = s.supplier_code
        WHEN MATCHED AND (t.supplier_name <> s.supplier_name OR t.country <> s.country
                          OR t.std_lead_time_days <> s.std_lead_time_days) THEN
            UPDATE SET t.supplier_name = s.supplier_name, t.country = s.country,
                       t.is_import = s.is_import, t.std_lead_time_days = s.std_lead_time_days
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (supplier_code, supplier_name, country, is_import, std_lead_time_days)
            VALUES (s.supplier_code, s.supplier_name, s.country, s.is_import, s.std_lead_time_days)
        OUTPUT $action INTO @chg;
        COMMIT;
        SELECT @ins = COUNT(CASE WHEN act = N'INSERT' THEN 1 END),
               @upd = COUNT(CASE WHEN act = N'UPDATE' THEN 1 END) FROM @chg;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_updated = @upd;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_product_group
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @load_id INT, @ins INT;
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_product_group', @load_id = @load_id OUTPUT;

    INSERT dw.dim_product_group (product_group, category)
    SELECT DISTINCT s.product_group, s.category
    FROM stg.product s
    WHERE s.product_group IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dw.dim_product_group g WHERE g.product_group = s.product_group);
    SET @ins = @@ROWCOUNT;

    EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins;
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dim_product
    @effective_date DATE
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @upd INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_dim_product', @load_id = @load_id OUTPUT;
    BEGIN TRY
        DROP TABLE IF EXISTS #src;

        SELECT s.product_code, s.product_name,
               ISNULL(g.product_group_key, -1) AS product_group_key,
               s.product_group, s.category, s.brand, s.muadil_id, s.lifecycle_status,
               s.list_price, s.launch_date, s.phaseout_date, s.sourcing_type,
               HASHBYTES('SHA2_256', CONCAT_WS(N'|',
                   s.product_name, s.product_group, s.category, s.brand, ISNULL(s.muadil_id, N''),
                   s.lifecycle_status, CONVERT(NVARCHAR(20), s.list_price),
                   ISNULL(CONVERT(NVARCHAR(10), s.launch_date, 23), N''),
                   ISNULL(CONVERT(NVARCHAR(10), s.phaseout_date, 23), N''),
                   s.sourcing_type)) AS row_hash
        INTO #src
        FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY product_code ORDER BY product_name) AS rn
              FROM stg.product) s
        LEFT JOIN dw.dim_product_group g ON g.product_group = s.product_group
        WHERE s.rn = 1;

        INSERT etl.dq_issue (load_id, source_table, issue_type, business_key, detail)
        SELECT @load_id, N'stg.product', 'DUPLICATE', product_code, N'Master''da birden fazla satır; ilki alındı'
        FROM stg.product GROUP BY product_code HAVING COUNT(*) > 1;

        BEGIN TRAN;

        UPDATE d
           SET product_name = s.product_name, product_group_key = s.product_group_key,
               product_group = s.product_group, category = s.category, brand = s.brand,
               muadil_id = s.muadil_id, lifecycle_status = s.lifecycle_status,
               list_price = s.list_price, launch_date = s.launch_date,
               phaseout_date = s.phaseout_date, sourcing_type = s.sourcing_type, row_hash = s.row_hash
          FROM dw.dim_product d
          JOIN #src s ON s.product_code = d.product_code
         WHERE d.is_current = 1 AND d.row_hash <> s.row_hash AND d.valid_from >= @effective_date;
        SET @upd = @@ROWCOUNT;

        UPDATE d
           SET valid_to = DATEADD(DAY, -1, @effective_date), is_current = 0
          FROM dw.dim_product d
          JOIN #src s ON s.product_code = d.product_code
         WHERE d.is_current = 1 AND d.row_hash <> s.row_hash AND d.valid_from < @effective_date;
        SET @upd += @@ROWCOUNT;

        INSERT dw.dim_product (product_code, product_name, product_group_key, product_group, category, brand,
                               muadil_id, lifecycle_status, list_price, launch_date, phaseout_date,
                               sourcing_type, valid_from, valid_to, is_current, row_hash)
        SELECT s.product_code, s.product_name, s.product_group_key, s.product_group, s.category, s.brand,
               s.muadil_id, s.lifecycle_status, s.list_price, s.launch_date, s.phaseout_date, s.sourcing_type,
               CASE WHEN EXISTS (SELECT 1 FROM dw.dim_product h WHERE h.product_code = s.product_code)
                    THEN @effective_date ELSE '1900-01-01' END,
               '9999-12-31', 1, s.row_hash
        FROM #src s
        WHERE NOT EXISTS (SELECT 1 FROM dw.dim_product d
                          WHERE d.product_code = s.product_code AND d.is_current = 1);
        SET @ins = @@ROWCOUNT;

        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_updated = @upd;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_sales
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000),
            @min_key INT, @max_key INT;
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_sales', @load_id = @load_id OUTPUT;
    BEGIN TRY
        DROP TABLE IF EXISTS #s;

        SELECT invoice_no, invoice_date, product_code, channel_code, warehouse_code, qty, net_amount,
               ROW_NUMBER() OVER (PARTITION BY invoice_no, product_code ORDER BY (SELECT NULL)) AS rn
        INTO #s
        FROM stg.sales
        WHERE invoice_date IS NOT NULL AND qty IS NOT NULL;

        INSERT etl.dq_issue (load_id, source_table, issue_type, business_key, detail)
        SELECT @load_id, N'stg.sales', 'DUPLICATE', CONCAT(invoice_no, N'|', product_code), N'Mükerrer fatura satırı elendi'
        FROM #s WHERE rn > 1;

        INSERT etl.dq_issue (load_id, source_table, issue_type, business_key, detail)
        SELECT @load_id, N'stg.sales', 'UNKNOWN_CHANNEL', CONCAT(s.invoice_no, N'|', s.product_code),
               CONCAT(N'Tanımsız kanal kodu: ', s.channel_code)
        FROM #s s
        WHERE s.rn = 1 AND NOT EXISTS (SELECT 1 FROM dw.dim_channel c WHERE c.channel_code = s.channel_code);

        INSERT etl.dq_issue (load_id, source_table, issue_type, business_key, detail)
        SELECT @load_id, N'stg.sales', 'UNKNOWN_PRODUCT', CONCAT(s.invoice_no, N'|', s.product_code),
               N'Ürün master''da yok veya fatura tarihinde geçerli versiyon yok'
        FROM #s s
        WHERE s.rn = 1 AND NOT EXISTS (SELECT 1 FROM dw.dim_product p
                                       WHERE p.product_code = s.product_code
                                         AND s.invoice_date BETWEEN p.valid_from AND p.valid_to);

        SELECT @min_key = CONVERT(INT, CONVERT(CHAR(8), MIN(invoice_date), 112)),
               @max_key = CONVERT(INT, CONVERT(CHAR(8), MAX(invoice_date), 112))
        FROM #s;

        BEGIN TRAN;
        DELETE FROM dw.fact_sales WHERE date_key BETWEEN @min_key AND @max_key;
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_sales (date_key, product_key, channel_key, warehouse_key, invoice_no,
                              is_return, qty, net_amount, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), s.invoice_date, 112)),
               ISNULL(p.product_key, -1),
               ISNULL(c.channel_key, -1),
               ISNULL(w.warehouse_key, -1),
               s.invoice_no,
               CASE WHEN s.qty < 0 THEN 1 ELSE 0 END,
               s.qty,
               ISNULL(s.net_amount, 0),
               @load_id
        FROM #s s
        LEFT JOIN dw.dim_product p   ON p.product_code = s.product_code
                                    AND s.invoice_date BETWEEN p.valid_from AND p.valid_to
        LEFT JOIN dw.dim_channel c   ON c.channel_code = s.channel_code
        LEFT JOIN dw.dim_warehouse w ON w.warehouse_code = s.warehouse_code
        WHERE s.rn = 1;
        SET @ins = @@ROWCOUNT;
        COMMIT;

        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_forecast
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_forecast', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        DELETE f
          FROM dw.fact_forecast f
         WHERE f.version_date_key IN (SELECT DISTINCT CONVERT(INT, CONVERT(CHAR(8), version_month, 112))
                                      FROM stg.forecast);
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_forecast (version_date_key, target_date_key, lag_month, product_key, channel_key,
                                 forecast_qty, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), s.version_month, 112)),
               CONVERT(INT, CONVERT(CHAR(8), s.target_month, 112)),
               DATEDIFF(MONTH, s.version_month, s.target_month),
               ISNULL(p.product_key, -1),
               ISNULL(c.channel_key, -1),
               SUM(s.forecast_qty),
               @load_id
        FROM stg.forecast s
        LEFT JOIN dw.dim_product p ON p.product_code = s.product_code
                                  AND s.version_month BETWEEN p.valid_from AND p.valid_to
        LEFT JOIN dw.dim_channel c ON c.channel_code = s.channel_code
        WHERE s.version_month IS NOT NULL AND s.target_month >= s.version_month
        GROUP BY s.version_month, s.target_month, ISNULL(p.product_key, -1), ISNULL(c.channel_key, -1);
        SET @ins = @@ROWCOUNT;
        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_budget
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_budget', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        DELETE f
          FROM dw.fact_budget f
          JOIN dw.dim_date d ON d.date_key = f.date_key
         WHERE d.[year] IN (SELECT DISTINCT budget_year FROM stg.budget);
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_budget (date_key, product_group_key, channel_key, budget_qty, budget_amount, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), DATEFROMPARTS(YEAR(s.budget_month), MONTH(s.budget_month), 1), 112)),
               ISNULL(g.product_group_key, -1),
               ISNULL(c.channel_key, -1),
               SUM(s.budget_qty),
               SUM(s.budget_amount),
               @load_id
        FROM stg.budget s
        LEFT JOIN dw.dim_product_group g ON g.product_group = s.product_group
        LEFT JOIN dw.dim_channel c       ON c.channel_code = s.channel_code
        WHERE s.budget_month IS NOT NULL
        GROUP BY DATEFROMPARTS(YEAR(s.budget_month), MONTH(s.budget_month), 1),
                 ISNULL(g.product_group_key, -1), ISNULL(c.channel_key, -1);
        SET @ins = @@ROWCOUNT;
        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_inventory
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_inventory', @load_id = @load_id OUTPUT;
    BEGIN TRY
        INSERT etl.dq_issue (load_id, source_table, issue_type, business_key, detail)
        SELECT @load_id, N'stg.inventory', 'AGING_MISMATCH',
               CONCAT(CONVERT(CHAR(10), snapshot_date, 23), N'|', product_code, N'|', warehouse_code),
               CONCAT(N'Stok=', on_hand_qty, N' kova toplamı=', qty_0_30 + qty_31_60 + qty_61_90 + qty_90_plus)
        FROM stg.inventory
        WHERE on_hand_qty <> qty_0_30 + qty_31_60 + qty_61_90 + qty_90_plus;

        BEGIN TRAN;
        DELETE f
          FROM dw.fact_inventory_snapshot f
         WHERE f.date_key IN (SELECT DISTINCT CONVERT(INT, CONVERT(CHAR(8), snapshot_date, 112)) FROM stg.inventory);
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_inventory_snapshot (date_key, product_key, warehouse_key, on_hand_qty,
                                           qty_0_30, qty_31_60, qty_61_90, qty_90_plus, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), s.snapshot_date, 112)),
               ISNULL(p.product_key, -1),
               ISNULL(w.warehouse_key, -1),
               SUM(s.on_hand_qty), SUM(s.qty_0_30), SUM(s.qty_31_60), SUM(s.qty_61_90), SUM(s.qty_90_plus),
               @load_id
        FROM stg.inventory s
        LEFT JOIN dw.dim_product p   ON p.product_code = s.product_code
                                    AND s.snapshot_date BETWEEN p.valid_from AND p.valid_to
        LEFT JOIN dw.dim_warehouse w ON w.warehouse_code = s.warehouse_code
        WHERE s.snapshot_date IS NOT NULL
        GROUP BY s.snapshot_date, ISNULL(p.product_key, -1), ISNULL(w.warehouse_key, -1);
        SET @ins = @@ROWCOUNT;
        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_purchase_order
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT, @upd INT, @err NVARCHAR(4000);
    DECLARE @chg TABLE (act NVARCHAR(10));
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_purchase_order', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        WITH src AS (
            SELECT s.po_no, s.po_line,
                   ISNULL(sp.supplier_key, -1) AS supplier_key,
                   ISNULL(p.product_key, -1)   AS product_key,
                   CONVERT(INT, CONVERT(CHAR(8), s.order_date, 112))    AS order_date_key,
                   CONVERT(INT, CONVERT(CHAR(8), s.promised_date, 112)) AS promised_date_key,
                   CONVERT(INT, CONVERT(CHAR(8), s.delivered_date, 112)) AS delivered_date_key,
                   s.ordered_qty,
                   ISNULL(s.delivered_qty, 0) AS delivered_qty,
                   DATEDIFF(DAY, s.promised_date, s.delivered_date) AS delay_days,
                   CASE WHEN s.delivered_date IS NULL THEN NULL
                        WHEN ABS(DATEDIFF(DAY, s.promised_date, s.delivered_date)) <= 1 THEN 1 ELSE 0 END AS is_on_time,
                   CASE WHEN s.delivered_date IS NULL THEN NULL
                        WHEN s.delivered_qty >= s.ordered_qty THEN 1 ELSE 0 END AS is_in_full,
                   ROW_NUMBER() OVER (PARTITION BY s.po_no, s.po_line ORDER BY s.delivered_date DESC) AS rn
            FROM stg.purchase_order s
            LEFT JOIN dw.dim_supplier sp ON sp.supplier_code = s.supplier_code
            LEFT JOIN dw.dim_product p   ON p.product_code = s.product_code
                                        AND s.order_date BETWEEN p.valid_from AND p.valid_to
            WHERE s.po_no IS NOT NULL
        )
        MERGE dw.fact_purchase_order AS t
        USING (SELECT * FROM src WHERE rn = 1) AS s
           ON t.po_no = s.po_no AND t.po_line = s.po_line
        WHEN MATCHED AND (ISNULL(t.delivered_date_key, 0) <> ISNULL(s.delivered_date_key, 0)
                          OR t.delivered_qty <> s.delivered_qty
                          OR t.promised_date_key <> s.promised_date_key) THEN
            UPDATE SET t.promised_date_key  = s.promised_date_key,
                       t.delivered_date_key = s.delivered_date_key,
                       t.delivered_qty      = s.delivered_qty,
                       t.delay_days         = s.delay_days,
                       t.is_on_time         = s.is_on_time,
                       t.is_in_full         = s.is_in_full,
                       t.updated_load_id    = @load_id
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (po_no, po_line, supplier_key, product_key, order_date_key, promised_date_key,
                    delivered_date_key, ordered_qty, delivered_qty, delay_days, is_on_time, is_in_full, load_id)
            VALUES (s.po_no, s.po_line, s.supplier_key, s.product_key, s.order_date_key, s.promised_date_key,
                    s.delivered_date_key, s.ordered_qty, s.delivered_qty, s.delay_days, s.is_on_time,
                    s.is_in_full, @load_id)
        OUTPUT $action INTO @chg;
        COMMIT;
        SELECT @ins = COUNT(CASE WHEN act = N'INSERT' THEN 1 END),
               @upd = COUNT(CASE WHEN act = N'UPDATE' THEN 1 END) FROM @chg;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_updated = @upd;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_ml_forecast
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_ml_forecast', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        DELETE f
          FROM dw.fact_ml_forecast f
         WHERE f.run_date_key IN (SELECT DISTINCT CONVERT(INT, CONVERT(CHAR(8), run_date, 112)) FROM stg.ml_forecast);
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_ml_forecast (run_date_key, target_date_key, product_group_key, channel_key,
                                    model_name, forecast_qty, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), s.run_date, 112)),
               CONVERT(INT, CONVERT(CHAR(8), s.target_month, 112)),
               ISNULL(g.product_group_key, -1),
               ISNULL(c.channel_key, -1),
               s.model_name,
               SUM(s.forecast_qty),
               @load_id
        FROM stg.ml_forecast s
        LEFT JOIN dw.dim_product_group g ON g.product_group = s.product_group
        LEFT JOIN dw.dim_channel c       ON c.channel_code = s.channel_code
        WHERE s.run_date IS NOT NULL
        GROUP BY s.run_date, s.target_month, ISNULL(g.product_group_key, -1), ISNULL(c.channel_key, -1), s.model_name;
        SET @ins = @@ROWCOUNT;
        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_fact_ml_backtest
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @load_id INT, @ins INT = 0, @del INT = 0, @err NVARCHAR(4000);
    EXEC etl.usp_log_start @proc_name = N'etl.usp_load_fact_ml_backtest', @load_id = @load_id OUTPUT;
    BEGIN TRY
        BEGIN TRAN;
        DELETE f
          FROM dw.fact_ml_backtest f
         WHERE f.run_date_key IN (SELECT DISTINCT CONVERT(INT, CONVERT(CHAR(8), run_date, 112)) FROM stg.ml_backtest);
        SET @del = @@ROWCOUNT;

        INSERT dw.fact_ml_backtest (run_date_key, target_date_key, product_group_key, channel_key,
                                    model_name, forecast_qty, actual_qty, load_id)
        SELECT CONVERT(INT, CONVERT(CHAR(8), s.run_date, 112)),
               CONVERT(INT, CONVERT(CHAR(8), s.target_month, 112)),
               ISNULL(g.product_group_key, -1),
               ISNULL(c.channel_key, -1),
               s.model_name,
               SUM(s.forecast_qty),
               SUM(s.actual_qty),
               @load_id
        FROM stg.ml_backtest s
        LEFT JOIN dw.dim_product_group g ON g.product_group = s.product_group
        LEFT JOIN dw.dim_channel c       ON c.channel_code = s.channel_code
        WHERE s.run_date IS NOT NULL
        GROUP BY s.run_date, s.target_month, ISNULL(g.product_group_key, -1), ISNULL(c.channel_key, -1), s.model_name;
        SET @ins = @@ROWCOUNT;
        COMMIT;
        EXEC etl.usp_log_end @load_id = @load_id, @rows_inserted = @ins, @rows_deleted = @del;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @err = ERROR_MESSAGE();
        EXEC etl.usp_log_end @load_id = @load_id, @status = 'FAILED', @error_message = @err;
        THROW;
    END CATCH
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_dimensions
    @effective_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    EXEC etl.usp_load_dim_date;
    EXEC etl.usp_load_dim_channel;
    EXEC etl.usp_load_dim_warehouse;
    EXEC etl.usp_load_dim_supplier;
    EXEC etl.usp_load_dim_product_group;
    EXEC etl.usp_load_dim_product @effective_date = @effective_date;
END;
GO

CREATE OR ALTER PROCEDURE etl.usp_load_facts
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM stg.sales)          EXEC etl.usp_load_fact_sales;
    IF EXISTS (SELECT 1 FROM stg.forecast)       EXEC etl.usp_load_fact_forecast;
    IF EXISTS (SELECT 1 FROM stg.budget)         EXEC etl.usp_load_fact_budget;
    IF EXISTS (SELECT 1 FROM stg.inventory)      EXEC etl.usp_load_fact_inventory;
    IF EXISTS (SELECT 1 FROM stg.purchase_order) EXEC etl.usp_load_fact_purchase_order;
    IF EXISTS (SELECT 1 FROM stg.ml_forecast)    EXEC etl.usp_load_fact_ml_forecast;
    IF EXISTS (SELECT 1 FROM stg.ml_backtest)    EXEC etl.usp_load_fact_ml_backtest;
END;
GO
