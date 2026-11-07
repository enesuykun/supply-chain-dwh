# Tahmin Modeli Sonuçları

Rolling-origin backtest, son 6 kapanmış ay (Nisan – Eylül 2026), 49 seri (ürün grubu × kanal).
Her hedef ay için modeller, planlama TS'sinin kesinleştiği andaki bilgiyle (hedef aydan 2 ay
öncesine kadar veri) eğitilir; planlama TS'si lag-1 versiyondur. Doğruluk `1 − WAPE`,
bias `Σ(tahmin − gerçekleşen) / Σ gerçekleşen`.

Sayılar `python data_generator/generate_data.py` (seed 42) ve `python forecasting/forecast_model.py`
ile yeniden üretilir.

## Genel karşılaştırma

| Model | Doğruluk | Bias | Yorum |
|---|---:|---:|---|
| **Hibrit (TS + HW)** | **%93,3** | +%3,9 | En doğru; TS'nin iyimserliğini yarıya indiriyor |
| Planlama TS | %90,8 | +%8,1 | En iyi tekil tahmin, sistematik olarak iyimser |
| Holt-Winters | %88,3 | −%0,4 | Neredeyse yansız |
| Mevsimsel naive | %82,2 | −%12,0 | |
| MA3 | %79,0 | −%7,2 | Mevsimselliği yakalayamıyor |

## Aylara göre doğruluk

| Hedef ay | Hibrit | Planlama TS | Holt-Winters | Mevsimsel naive | MA3 |
|---|---:|---:|---:|---:|---:|
| 2026-04 | %92,3 | %90,0 | %87,8 | %83,3 | %73,0 |
| 2026-05 | %91,3 | %91,0 | %85,4 | %81,2 | %67,1 |
| 2026-06 | %95,5 | %90,8 | %86,8 | %80,5 | %71,2 |
| 2026-07 | %94,7 | %89,9 | %91,4 | %82,8 | %87,4 |
| 2026-08 | %91,1 | %90,1 | %87,9 | %82,4 | %89,9 |
| 2026-09 | %94,2 | %92,6 | %90,6 | %83,4 | %85,9 |

Hibrit altı ayın altısında da planlama TS'sinden daha doğru.

## İleri tahminde seçilen modeller

Her seri için backtest'te en düşük WAPE'yi veren model seçilip Ekim 2026 – Şubat 2027 tahmin edilir.
Hibrit, serinin tüm ufuk için güncel planlama TS'si varsa adaydır.

| Model | Seri sayısı |
|---|---:|
| Hibrit (TS + HW) | 40 |
| MA3 | 4 |
| Mevsimsel naive | 3 |
| Holt-Winters | 2 |

## Sınırlar

- Backtest'te hibrit yalnızca lag-1 TS ile ölçülüyor; ileri tahminde ise en güncel TS
  versiyonu (lag 1–5) kullanılıyor. Lag 2–5 için hibritin doğruluğu henüz ölçülmedi.
- Seviye ürün grubu × kanal; SKU seviyesine inmek yol haritasında.

## Nerede izlenir

| Katman | Kaynak |
|---|---|
| Dosya | `data/output/model_comparison.csv`, `data/output/ml_backtest.csv`, `data/output/ml_forecast.csv` |
| SQL | `rpt.v_ml_model_comparison` (son çalıştırma, model bazında), `dw.fact_ml_backtest`, `dw.fact_ml_forecast` |
| Power BI | `fact_ml_backtest` + `Model Doğruluk %`, `Model Bias %`, `Model Doğruluk Farkı vs TS`; `ML Tahmin` |

Power BI'da `model_name` eksene, `Model Doğruluk %` değere konduğunda yukarıdaki genel tablo;
`dim_date[month_start]` veya ürün grubu / kanal eklendiğinde kırılımlar elde edilir.
