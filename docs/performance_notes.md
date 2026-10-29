# Performans Çalışması — Ölçüm Notları

`sql/05_performance_tuning.sql` scriptini kendi ortamınızda adım adım çalıştırıp
`SET STATISTICS IO, TIME ON` çıktısındaki değerleri aşağıya işleyin. Değerler donanıma
göre değişir; önemli olan önce/sonra oranıdır.

**Ortam:** SQL Server 20__ · __ çekirdek · __ GB RAM · fact_sales satır sayısı: ______

| Adım | Sorgu | Önce: logical reads | Önce: CPU (ms) | Sonra: logical reads | Sonra: CPU (ms) | Not |
|---|---|---|---|---|---|---|
| 1 → 3 | 2025 grup × kanal × ay satış | | | | | Heap → Clustered Columnstore |
| 2 | Yıl filtresi | | | | | `YEAR(CONVERT(...))` → `date_key BETWEEN` |
| 4 | Tedarikçinin açık siparişleri | | | | | Covering index, key lookup yok |
| 6 | Ürün başına son stok | | | | | Correlated subquery → `ROW_NUMBER` |

## Gözlemler

- Execution plan'de columnstore sonrası **Batch** execution mode'u görülüyor mu?
- `sys.dm_db_column_store_row_group_physical_stats` çıktısında rowgroup sayısı ve
  `COMPRESSED` durumu.
- Query Store'da en yüksek ortalama logical read'e sahip ilk 3 sorgu.
