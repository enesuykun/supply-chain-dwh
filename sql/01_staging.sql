USE SupplyChainDW;
GO

DROP TABLE IF EXISTS stg.product, stg.channel, stg.warehouse, stg.supplier,
                     stg.sales, stg.forecast, stg.budget, stg.inventory,
                     stg.purchase_order, stg.ml_forecast;
GO

CREATE TABLE stg.product (
    product_code      NVARCHAR(20)  NOT NULL,
    product_name      NVARCHAR(100) NULL,
    product_group     NVARCHAR(50)  NULL,
    category          NVARCHAR(30)  NULL,
    brand             NVARCHAR(30)  NULL,
    muadil_id         NVARCHAR(20)  NULL,
    lifecycle_status  NVARCHAR(20)  NULL,
    list_price        DECIMAL(12,2) NULL,
    launch_date       DATE          NULL,
    phaseout_date     DATE          NULL,
    sourcing_type     NVARCHAR(20)  NULL
);

CREATE TABLE stg.channel (
    channel_code  NVARCHAR(10) NOT NULL,
    channel_name  NVARCHAR(50) NULL,
    channel_type  NVARCHAR(20) NULL
);

CREATE TABLE stg.warehouse (
    warehouse_code  NVARCHAR(10) NOT NULL,
    warehouse_name  NVARCHAR(60) NULL,
    city            NVARCHAR(40) NULL,
    region          NVARCHAR(40) NULL
);

CREATE TABLE stg.supplier (
    supplier_code       NVARCHAR(10)  NOT NULL,
    supplier_name       NVARCHAR(100) NULL,
    country             NVARCHAR(40)  NULL,
    std_lead_time_days  INT           NULL
);

CREATE TABLE stg.sales (
    invoice_no      NVARCHAR(20)  NULL,
    invoice_date    DATE          NULL,
    product_code    NVARCHAR(20)  NULL,
    channel_code    NVARCHAR(10)  NULL,
    warehouse_code  NVARCHAR(10)  NULL,
    qty             INT           NULL,
    net_amount      DECIMAL(14,2) NULL
);

CREATE TABLE stg.forecast (
    version_month  DATE         NULL,
    target_month   DATE         NULL,
    product_code   NVARCHAR(20) NULL,
    channel_code   NVARCHAR(10) NULL,
    forecast_qty   INT          NULL
);

CREATE TABLE stg.budget (
    budget_year    INT           NULL,
    budget_month   DATE          NULL,
    product_group  NVARCHAR(50)  NULL,
    channel_code   NVARCHAR(10)  NULL,
    budget_qty     INT           NULL,
    budget_amount  DECIMAL(16,2) NULL
);

CREATE TABLE stg.inventory (
    snapshot_date   DATE         NULL,
    product_code    NVARCHAR(20) NULL,
    warehouse_code  NVARCHAR(10) NULL,
    on_hand_qty     INT          NULL,
    qty_0_30        INT          NULL,
    qty_31_60       INT          NULL,
    qty_61_90       INT          NULL,
    qty_90_plus     INT          NULL
);

CREATE TABLE stg.purchase_order (
    po_no           NVARCHAR(20) NULL,
    po_line         INT          NULL,
    supplier_code   NVARCHAR(10) NULL,
    product_code    NVARCHAR(20) NULL,
    order_date      DATE         NULL,
    promised_date   DATE         NULL,
    delivered_date  DATE         NULL,
    ordered_qty     INT          NULL,
    delivered_qty   INT          NULL
);

CREATE TABLE stg.ml_forecast (
    run_date       DATE           NULL,
    target_month   DATE           NULL,
    product_group  NVARCHAR(50)   NULL,
    channel_code   NVARCHAR(10)   NULL,
    model_name     NVARCHAR(40)   NULL,
    forecast_qty   DECIMAL(12,2)  NULL
);
GO
