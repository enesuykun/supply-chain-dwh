# Veri Modeli

Star schema; olgu tabloları ortak boyutları (tarih, ürün, kanal) paylaşır, böylece
satış, TS, bütçe ve stok aynı rapor üzerinde tutarlı biçimde kesişir (conformed dimensions).

```mermaid
erDiagram
    dim_date ||--o{ fact_sales : date_key
    dim_product ||--o{ fact_sales : product_key
    dim_channel ||--o{ fact_sales : channel_key
    dim_warehouse ||--o{ fact_sales : warehouse_key

    dim_date ||--o{ fact_forecast : "target / version"
    dim_product ||--o{ fact_forecast : product_key
    dim_channel ||--o{ fact_forecast : channel_key

    dim_date ||--o{ fact_budget : date_key
    dim_product_group ||--o{ fact_budget : product_group_key
    dim_channel ||--o{ fact_budget : channel_key

    dim_date ||--o{ fact_inventory_snapshot : date_key
    dim_product ||--o{ fact_inventory_snapshot : product_key
    dim_warehouse ||--o{ fact_inventory_snapshot : warehouse_key

    dim_supplier ||--o{ fact_purchase_order : supplier_key
    dim_product ||--o{ fact_purchase_order : product_key
    dim_date ||--o{ fact_purchase_order : "order / promised / delivered"

    dim_product_group ||--o{ dim_product : product_group_key
    dim_product_group ||--o{ fact_ml_forecast : product_group_key
    dim_channel ||--o{ fact_ml_forecast : channel_key

    dim_product {
        int product_key PK
        string product_code "iş anahtarı"
        string product_group
        string muadil_id "eşdeğer ürün ailesi"
        string lifecycle_status
        decimal list_price
        date valid_from "SCD2"
        date valid_to "SCD2"
        bit is_current "SCD2"
    }
    fact_sales {
        int date_key FK
        int product_key FK
        int channel_key FK
        int warehouse_key FK
        string invoice_no "degenerate dim"
        bit is_return
        int qty
        decimal net_amount
    }
    fact_forecast {
        int version_date_key FK
        int target_date_key FK
        tinyint lag_month
        int product_key FK
        int channel_key FK
        int forecast_qty
    }
    fact_purchase_order {
        string po_no PK
        int po_line PK
        int promised_date_key
        int delivered_date_key
        int delay_days
        bit is_on_time
        bit is_in_full
        bit is_otif "computed"
    }
```

## Olgu tabloları ve grain

| Tablo | Grain | Tip | Yükleme stratejisi |
|---|---|---|---|
| `fact_sales` | Fatura satırı | Transaction | Staging'deki tarih aralığını sil + ekle |
| `fact_forecast` | Versiyon ay × hedef ay × ürün × kanal | Snapshot (versiyonlu) | Gelen versiyonları sil + ekle |
| `fact_budget` | Ay × ürün grubu × kanal | Plan | Gelen bütçe yıllarını sil + ekle |
| `fact_inventory_snapshot` | Ay sonu × ürün × depo | Periodic snapshot | Gelen snapshot tarihlerini sil + ekle |
| `fact_purchase_order` | Sipariş satırı | Accumulating snapshot | `MERGE` (teslimat gerçekleştikçe güncellenir) |
| `fact_ml_forecast` | Çalıştırma × hedef ay × grup × kanal × model | Snapshot | Gelen çalıştırma tarihini sil + ekle |

## Tasarım kararları

- **SCD Type 2 ürün boyutu.** Liste fiyatı ve yaşam döngüsü statüsü zamanla değişir.
  Temmuz 2025 öncesi satışlar eski fiyat/statüye, sonrası yenisine bağlanır; geçmiş
  raporlar "o günkü" ürün bilgisiyle tekrar üretilebilir. Değişiklik, kolonların
  SHA-256 hash'i karşılaştırılarak tespit edilir.
- **Bütçe ürün grubu seviyesinde.** Bütçe SKU bazında yapılmadığı için ayrı bir
  `dim_product_group` boyutu var; ürün boyutu da bu boyuta bağlı. Böylece bütçe ile
  SKU bazlı satış aynı grup seviyesinde kesişir.
- **Unknown member (-1).** Eşleşmeyen kodlar olgudan düşürülmez; toplam tutarlar kaynak
  sistemle mutabık kalır, sorunlu satırlar `etl.dq_issue` üzerinden izlenir.
- **Lag kolonu.** `fact_forecast.lag_month` tahminin kaç ay önceden yapıldığını tutar;
  "1 ay önceki TS'ye göre doğruluk" gibi planlama KPI'ları doğrudan filtrelenebilir.
- **OTIF kuralı.** Teslim söz verilen tarihin ±1 günü içinde (rampa randevu disiplini)
  ve sipariş miktarı kadar ise satır OTIF sayılır; `is_otif` hesaplanmış (persisted) kolon.

## Power BI ilişkileri

| Boyut | Olgu | Not |
|---|---|---|
| `dim_date[date_key]` | `fact_sales[date_key]`, `fact_budget[date_key]`, `fact_inventory_snapshot[date_key]` | |
| `dim_date[date_key]` | `fact_forecast[target_date_key]` | aktif |
| `dim_date[date_key]` | `fact_forecast[version_date_key]` | pasif, `USERELATIONSHIP` ile |
| `dim_date[date_key]` | `fact_purchase_order[delivered_date_key]`, `fact_ml_forecast[target_date_key]` | |
| `dim_product[product_key]` | `fact_sales`, `fact_forecast`, `fact_inventory_snapshot`, `fact_purchase_order` | |
| `dim_product_group[product_group_key]` | `dim_product`, `fact_budget`, `fact_ml_forecast` | |
| `dim_channel[channel_key]` | `fact_sales`, `fact_forecast`, `fact_budget`, `fact_ml_forecast` | |
| `dim_supplier[supplier_key]` | `fact_purchase_order` | |

`dim_date` tarih tablosu olarak işaretlenir. Tahmin doğruluğu ölçüleri için `rpt.v_forecast_vs_actual` ayrıca içe aktarılır.
