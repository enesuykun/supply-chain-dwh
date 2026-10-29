USE SupplyChainDW;
GO

DROP TABLE IF EXISTS dw.fact_sales, dw.fact_forecast, dw.fact_budget,
                     dw.fact_inventory_snapshot, dw.fact_purchase_order, dw.fact_ml_forecast;
DROP TABLE IF EXISTS dw.dim_product, dw.dim_product_group, dw.dim_channel,
                     dw.dim_warehouse, dw.dim_supplier, dw.dim_date;
DROP TABLE IF EXISTS etl.dq_issue, etl.load_log;
GO

CREATE TABLE etl.load_log (
    load_id        INT IDENTITY(1,1) PRIMARY KEY,
    proc_name      SYSNAME        NOT NULL,
    start_time     DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
    end_time       DATETIME2(0)   NULL,
    rows_inserted  INT            NULL,
    rows_updated   INT            NULL,
    rows_deleted   INT            NULL,
    status         VARCHAR(10)    NOT NULL DEFAULT 'RUNNING',
    error_message  NVARCHAR(4000) NULL
);

CREATE TABLE etl.dq_issue (
    issue_id      INT IDENTITY(1,1) PRIMARY KEY,
    load_id       INT            NULL,
    source_table  SYSNAME        NOT NULL,
    issue_type    VARCHAR(40)    NOT NULL,
    business_key  NVARCHAR(100)  NULL,
    detail        NVARCHAR(400)  NULL,
    logged_at     DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE TABLE dw.dim_date (
    date_key        INT          NOT NULL PRIMARY KEY,
    full_date       DATE         NOT NULL UNIQUE,
    [year]          SMALLINT     NOT NULL,
    [quarter]       TINYINT      NOT NULL,
    [month]         TINYINT      NOT NULL,
    month_name_tr   NVARCHAR(10) NOT NULL,
    year_month      CHAR(7)      NOT NULL,
    month_start     DATE         NOT NULL,
    month_end       DATE         NOT NULL,
    days_in_month   TINYINT      NOT NULL,
    iso_week        TINYINT      NOT NULL,
    day_of_week     TINYINT      NOT NULL,
    day_name_tr     NVARCHAR(10) NOT NULL,
    is_weekend      BIT          NOT NULL,
    is_month_start  BIT          NOT NULL
);

CREATE TABLE dw.dim_product_group (
    product_group_key  INT IDENTITY(1,1) PRIMARY KEY,
    product_group      NVARCHAR(50) NOT NULL UNIQUE,
    category           NVARCHAR(30) NOT NULL
);

CREATE TABLE dw.dim_product (
    product_key        INT IDENTITY(1,1) PRIMARY KEY,
    product_code       NVARCHAR(20)  NOT NULL,
    product_name       NVARCHAR(100) NOT NULL,
    product_group_key  INT           NOT NULL,
    product_group      NVARCHAR(50)  NOT NULL,
    category           NVARCHAR(30)  NOT NULL,
    brand              NVARCHAR(30)  NOT NULL,
    muadil_id          NVARCHAR(20)  NULL,
    lifecycle_status   NVARCHAR(20)  NOT NULL,
    list_price         DECIMAL(12,2) NOT NULL,
    launch_date        DATE          NULL,
    phaseout_date      DATE          NULL,
    sourcing_type      NVARCHAR(20)  NOT NULL,
    valid_from         DATE          NOT NULL,
    valid_to           DATE          NOT NULL DEFAULT '9999-12-31',
    is_current         BIT           NOT NULL DEFAULT 1,
    row_hash           VARBINARY(32) NULL
);
CREATE UNIQUE INDEX ux_dim_product_code_from ON dw.dim_product (product_code, valid_from);
CREATE INDEX ix_dim_product_current ON dw.dim_product (product_code) WHERE is_current = 1;

CREATE TABLE dw.dim_channel (
    channel_key   INT IDENTITY(1,1) PRIMARY KEY,
    channel_code  NVARCHAR(10) NOT NULL UNIQUE,
    channel_name  NVARCHAR(50) NOT NULL,
    channel_type  NVARCHAR(20) NOT NULL
);

CREATE TABLE dw.dim_warehouse (
    warehouse_key   INT IDENTITY(1,1) PRIMARY KEY,
    warehouse_code  NVARCHAR(10) NOT NULL UNIQUE,
    warehouse_name  NVARCHAR(60) NOT NULL,
    city            NVARCHAR(40) NOT NULL,
    region          NVARCHAR(40) NOT NULL
);

CREATE TABLE dw.dim_supplier (
    supplier_key        INT IDENTITY(1,1) PRIMARY KEY,
    supplier_code       NVARCHAR(10)  NOT NULL UNIQUE,
    supplier_name       NVARCHAR(100) NOT NULL,
    country             NVARCHAR(40)  NOT NULL,
    is_import           BIT           NOT NULL,
    std_lead_time_days  INT           NOT NULL
);
GO

SET IDENTITY_INSERT dw.dim_product_group ON;
INSERT dw.dim_product_group (product_group_key, product_group, category) VALUES (-1, N'Bilinmeyen', N'Bilinmeyen');
SET IDENTITY_INSERT dw.dim_product_group OFF;

SET IDENTITY_INSERT dw.dim_product ON;
INSERT dw.dim_product (product_key, product_code, product_name, product_group_key, product_group, category, brand,
                       lifecycle_status, list_price, sourcing_type, valid_from)
VALUES (-1, N'N/A', N'Bilinmeyen Ürün', -1, N'Bilinmeyen', N'Bilinmeyen', N'Bilinmeyen', N'Bilinmeyen', 0, N'Bilinmeyen', '1900-01-01');
SET IDENTITY_INSERT dw.dim_product OFF;

SET IDENTITY_INSERT dw.dim_channel ON;
INSERT dw.dim_channel (channel_key, channel_code, channel_name, channel_type) VALUES (-1, N'N/A', N'Bilinmeyen Kanal', N'Bilinmeyen');
SET IDENTITY_INSERT dw.dim_channel OFF;

SET IDENTITY_INSERT dw.dim_warehouse ON;
INSERT dw.dim_warehouse (warehouse_key, warehouse_code, warehouse_name, city, region) VALUES (-1, N'N/A', N'Bilinmeyen Depo', N'-', N'-');
SET IDENTITY_INSERT dw.dim_warehouse OFF;

SET IDENTITY_INSERT dw.dim_supplier ON;
INSERT dw.dim_supplier (supplier_key, supplier_code, supplier_name, country, is_import, std_lead_time_days) VALUES (-1, N'N/A', N'Bilinmeyen Tedarikçi', N'-', 0, 0);
SET IDENTITY_INSERT dw.dim_supplier OFF;
GO

CREATE TABLE dw.fact_sales (
    date_key       INT           NOT NULL,
    product_key    INT           NOT NULL,
    channel_key    INT           NOT NULL,
    warehouse_key  INT           NOT NULL,
    invoice_no     NVARCHAR(20)  NOT NULL,
    is_return      BIT           NOT NULL,
    qty            INT           NOT NULL,
    net_amount     DECIMAL(14,2) NOT NULL,
    load_id        INT           NOT NULL
);

CREATE TABLE dw.fact_forecast (
    version_date_key  INT NOT NULL,                        -- TS'nin kesinleştiği ay (ay başı)
    target_date_key   INT NOT NULL,
    lag_month         TINYINT NOT NULL,
    product_key       INT NOT NULL,
    channel_key       INT NOT NULL,
    forecast_qty      INT NOT NULL,
    load_id           INT NOT NULL,
    CONSTRAINT pk_fact_forecast PRIMARY KEY (version_date_key, target_date_key, product_key, channel_key)
);

CREATE TABLE dw.fact_budget (
    date_key           INT NOT NULL,
    product_group_key  INT NOT NULL,
    channel_key        INT NOT NULL,
    budget_qty         INT NOT NULL,
    budget_amount      DECIMAL(16,2) NOT NULL,
    load_id            INT NOT NULL,
    CONSTRAINT pk_fact_budget PRIMARY KEY (date_key, product_group_key, channel_key)
);

CREATE TABLE dw.fact_inventory_snapshot (
    date_key       INT NOT NULL,
    product_key    INT NOT NULL,
    warehouse_key  INT NOT NULL,
    on_hand_qty    INT NOT NULL,
    qty_0_30       INT NOT NULL,
    qty_31_60      INT NOT NULL,
    qty_61_90      INT NOT NULL,
    qty_90_plus    INT NOT NULL,
    load_id        INT NOT NULL,
    CONSTRAINT pk_fact_inventory PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE dw.fact_purchase_order (
    po_no              NVARCHAR(20) NOT NULL,
    po_line            INT          NOT NULL,
    supplier_key       INT          NOT NULL,
    product_key        INT          NOT NULL,
    order_date_key     INT          NOT NULL,
    promised_date_key  INT          NOT NULL,
    delivered_date_key INT          NULL,
    ordered_qty        INT          NOT NULL,
    delivered_qty      INT          NOT NULL,
    delay_days         INT          NULL,
    is_on_time         BIT          NULL,
    is_in_full         BIT          NULL,
    is_otif            AS (CONVERT(BIT, CASE WHEN is_on_time = 1 AND is_in_full = 1 THEN 1 ELSE 0 END)) PERSISTED,
    load_id            INT          NOT NULL,
    updated_load_id    INT          NULL,
    CONSTRAINT pk_fact_po PRIMARY KEY (po_no, po_line)
);

CREATE TABLE dw.fact_ml_forecast (
    run_date_key       INT NOT NULL,
    target_date_key    INT NOT NULL,
    product_group_key  INT NOT NULL,
    channel_key        INT NOT NULL,
    model_name         NVARCHAR(40) NOT NULL,
    forecast_qty       DECIMAL(12,2) NOT NULL,
    load_id            INT NOT NULL,
    CONSTRAINT pk_fact_ml_forecast PRIMARY KEY (run_date_key, target_date_key, product_group_key, channel_key, model_name)
);
GO

ALTER TABLE dw.fact_forecast ADD
    CONSTRAINT fk_fc_product FOREIGN KEY (product_key) REFERENCES dw.dim_product (product_key),
    CONSTRAINT fk_fc_channel FOREIGN KEY (channel_key) REFERENCES dw.dim_channel (channel_key);
ALTER TABLE dw.fact_budget ADD
    CONSTRAINT fk_bd_group   FOREIGN KEY (product_group_key) REFERENCES dw.dim_product_group (product_group_key),
    CONSTRAINT fk_bd_channel FOREIGN KEY (channel_key) REFERENCES dw.dim_channel (channel_key);
ALTER TABLE dw.fact_inventory_snapshot ADD
    CONSTRAINT fk_inv_product   FOREIGN KEY (product_key) REFERENCES dw.dim_product (product_key),
    CONSTRAINT fk_inv_warehouse FOREIGN KEY (warehouse_key) REFERENCES dw.dim_warehouse (warehouse_key);
ALTER TABLE dw.fact_purchase_order ADD
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_key) REFERENCES dw.dim_supplier (supplier_key),
    CONSTRAINT fk_po_product  FOREIGN KEY (product_key) REFERENCES dw.dim_product (product_key);
GO
