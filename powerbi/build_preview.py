"""Power BI yönetici özeti sayfasının statik HTML önizlemesini üretir.

Yerleşim, renkler ve eşikler docs/powerbi_dashboard_spec.md ile aynıdır; sayılar SupplyChainDW
view'larından okunur. Çıktı gerçek bir Power BI raporu değildir: sayfanın belirtime göre nasıl
görüneceğini gösterir.

    python powerbi/build_preview.py            # -> docs/dashboard_preview.html
"""
from __future__ import annotations

import html
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "etl"))
import run_pipeline as rp  # noqa: E402

OUT = ROOT / "docs" / "dashboard_preview.html"
MONTHS_TR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
BLUE, ORANGE, NEUTRAL = "#2a78d6", "#eb6834", "#b9b8b3"
GOOD, WARN, BAD = "#1baf7a", "#e0a100", "#e34948"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
HYBRID, PLANNER = "Hibrit(TS+HW)", "PlanlamaTS"
OTIF_TARGET = 0.95


def tr_num(x: float, d: int = 0) -> str:
    q = Decimal(str(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    s = f"{q:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x: float, d: int = 1, sign: bool = False) -> str:
    return f"{'+' if sign and x >= 0 else ''}{'-' if x < 0 else ''}%{tr_num(abs(x) * 100, d)}".replace("--", "-")


def mlabel(d: date, year: bool = True) -> str:
    return f"{MONTHS_TR[d.month - 1]} {d.year}" if year else MONTHS_TR[d.month - 1]


def e(s: object) -> str:
    return html.escape(str(s))


# ------------------------------------------------------------------ veri
def fetch() -> dict:
    cur = rp.connect(rp.DB_NAME).cursor()

    def rows(sql: str) -> list:
        return cur.execute(sql).fetchall()

    last = rows("SELECT MAX(month_start) FROM rpt.v_sales_monthly")[0][0]
    last_invoice = rows("""SELECT MAX(d.full_date) FROM dw.fact_sales f
                           JOIN dw.dim_date d ON d.date_key = f.date_key""")[0][0]
    prev_year = date(last.year - 1, last.month, 1)
    sales = dict(rows("SELECT month_start, SUM(net_qty) FROM rpt.v_sales_monthly GROUP BY month_start"))
    ytd = rows(f"""SELECT SUM(actual_qty), SUM(budget_qty), SUM(ts_qty) FROM rpt.v_budget_ts_actual
                   WHERE month_start BETWEEN '{last.year}-01-01' AND '{last:%Y-%m-%d}'""")[0]
    series = rows(f"""SELECT month_start, SUM(actual_qty), SUM(budget_qty), SUM(ts_qty) FROM rpt.v_budget_ts_actual
                      WHERE month_start BETWEEN DATEADD(MONTH, -20, '{last:%Y-%m-%d}') AND '{last:%Y-%m-%d}'
                      GROUP BY month_start ORDER BY month_start""")
    models = rows("""SELECT model_name, forecast_accuracy, forecast_bias, series_count, first_target_month,
                            last_target_month FROM rpt.v_ml_model_comparison ORDER BY forecast_accuracy DESC""")
    stock_month = rows("SELECT MAX(month_start) FROM rpt.v_stock_cover")[0][0]
    stock_total = rows(f"""SELECT SUM(on_hand_qty), SUM(qty_90_plus), SUM(avg_sales_3m) FROM rpt.v_stock_cover
                           WHERE month_start = '{stock_month:%Y-%m-%d}'""")[0]
    stock_groups = rows(f"""SELECT product_group, SUM(on_hand_qty) / NULLIF(SUM(avg_sales_3m), 0) FROM rpt.v_stock_cover
                            WHERE month_start = '{stock_month:%Y-%m-%d}' GROUP BY product_group ORDER BY 2 DESC""")
    stock_flags = dict(rows(f"""SELECT LEFT(stock_status, 5), COUNT(DISTINCT product_code) FROM rpt.v_stock_cover
                                WHERE month_start = '{stock_month:%Y-%m-%d}' GROUP BY LEFT(stock_status, 5)"""))
    suppliers = rows("""SELECT supplier_name, SUM(otif_rate * delivered_lines) / SUM(delivered_lines)
                        FROM rpt.v_supplier_otif GROUP BY supplier_name ORDER BY 2""")
    otif_all = rows("""SELECT AVG(CAST(is_otif AS FLOAT)) FROM dw.fact_purchase_order
                       WHERE delivered_date_key IS NOT NULL""")[0][0]
    dq = dict(rows("""SELECT issue_type, issue_count FROM rpt.v_dq_summary
                      WHERE proc_name = 'etl.usp_load_fact_sales'
                        AND load_id = (SELECT MAX(load_id) FROM rpt.v_dq_summary
                                       WHERE proc_name = 'etl.usp_load_fact_sales')"""))
    return {"last": last, "last_invoice": last_invoice, "sales_now": sales[last], "sales_prev": sales[prev_year],
            "ytd": ytd, "series": series, "models": models, "stock_month": stock_month, "stock_total": stock_total,
            "stock_groups": stock_groups, "stock_flags": stock_flags, "suppliers": suppliers,
            "otif_all": float(otif_all), "dq": dq}


# ------------------------------------------------------------------ SVG
def hbar(items, w, h, vmin, vmax, ticks, tick_fmt, label_w, lines=()):
    """items: (etiket, değer, renk, değer_etiketi). Yatay çubuk; sabit çizgiler (değer, etiket, renk)."""
    left, right, top, bottom = label_w, 70, 16 if lines else 4, 22
    pw, ph = w - left - right, h - top - bottom
    step = ph / len(items)
    bar = min(step * 0.62, 26)

    def x(v):
        return left + (v - vmin) / (vmax - vmin) * pw

    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    for t in ticks:
        out.append(f'<line x1="{x(t):.1f}" y1="{top}" x2="{x(t):.1f}" y2="{top + ph}" stroke="{GRID}"/>')
        out.append(f'<text x="{x(t):.1f}" y="{h - 6}" text-anchor="middle" class="ax">{e(tick_fmt(t))}</text>')
    for i, (name, val, color, text) in enumerate(items):
        cy = top + step * i + step / 2
        out.append(f'<text x="{left - 8}" y="{cy + 4:.1f}" text-anchor="end" class="lb">{e(name)}</text>')
        out.append(f'<rect x="{left}" y="{cy - bar / 2:.1f}" width="{max(x(val) - left, 1):.1f}" height="{bar:.1f}" '
                   f'rx="2" fill="{color}"/>')
        out.append(f'<text x="{x(val) + 6:.1f}" y="{cy + 4:.1f}" class="vl">{e(text)}</text>')
    for val, label, color in lines:
        out.append(f'<line x1="{x(val):.1f}" y1="{top}" x2="{x(val):.1f}" y2="{top + ph}" stroke="{color}" '
                   f'stroke-dasharray="5 4" stroke-width="1.5"/>')
        out.append(f'<text x="{x(val):.1f}" y="{top - 4}" text-anchor="middle" class="ref" fill="{color}">{e(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def line_chart(w, h, labels, series, ymax):
    """series: (renk, değerler, kesikli_mi). Yalnızca son nokta etiketlenir."""
    left, right, top, bottom = 44, 56, 8, 24
    pw, ph = w - left - right, h - top - bottom
    n = len(labels)

    def x(i):
        return left + i / (n - 1) * pw

    def y(v):
        return top + ph - v / ymax * ph

    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    for k in range(5):
        v = ymax * k / 4
        out.append(f'<line x1="{left}" y1="{y(v):.1f}" x2="{left + pw}" y2="{y(v):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="ax">{tr_num(v)}</text>')
    for i in range(0, n, 3):
        out.append(f'<text x="{x(i):.1f}" y="{h - 6}" text-anchor="middle" class="ax">{e(labels[i])}</text>')
    ends = sorted(((y(vals[-1]), k) for k, (_, vals, _) in enumerate(series)))
    label_y, prev = {}, -99.0
    for yy, k in ends:
        prev = max(yy, prev + 13)
        label_y[k] = prev
    for k, (color, vals, dashed) in enumerate(series):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2"{dash}/>')
        out.append(f'<circle cx="{x(n - 1):.1f}" cy="{y(vals[-1]):.1f}" r="3.5" fill="{color}"/>')
        out.append(f'<text x="{x(n - 1) + 8:.1f}" y="{label_y[k] + 4:.1f}" class="vl">{tr_num(vals[-1])}</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ sayfa
def rule_color(v, lo, hi):
    return GOOD if v >= hi else WARN if v >= lo else BAD


def build(d: dict) -> str:
    last = d["last"]
    lm = mlabel(last)
    models = {m[0]: m for m in d["models"]}
    ts, hy = models[PLANNER], models[HYBRID]
    n_series = ts[3]
    f_month, l_month = ts[4], ts[5]
    n_months = (l_month.year - f_month.year) * 12 + l_month.month - f_month.month + 1

    yoy = d["sales_now"] / d["sales_prev"] - 1
    act, bud, tsq = (float(v) for v in d["ytd"])
    achieve, ts_to_bud = act / bud, tsq / bud
    on_hand, q90, avg3 = (float(v) for v in d["stock_total"])
    cover = on_hand / avg3
    cover_color = GOOD if 0.5 <= cover <= 3 else BAD
    otif = d["otif_all"]

    cards = [
        (f"Satış, {lm}", tr_num(d["sales_now"]), f"{'▲' if yoy >= 0 else '▼'} {pct(yoy, 1, True)} geçen yıla göre",
         GOOD if yoy >= 0 else BAD),
        (f"Bütçe, Oca–{mlabel(last, False)} {last.year}", pct(achieve), f"TS bütçenin {pct(ts_to_bud)}'ü",
         rule_color(achieve, 0.95, 1.0)),
        ("Planlama TS doğruluğu", pct(ts[1]), f"sapma {pct(ts[2], 1, True)}", rule_color(float(ts[1]), 0.8, 0.9)),
        ("Hibrit model doğruluğu", pct(hy[1]), f"TS'ye göre {pct(float(hy[1]) - float(ts[1]), 1, True)}",
         rule_color(float(hy[1]), 0.8, 0.9)),
        (f"Stok kapsama, {lm}", f"{tr_num(cover, 2)} ay", f"90 günü aşan {pct(q90 / on_hand)}", cover_color),
        ("OTIF, tüm dönem", pct(otif), f"Hedef {pct(OTIF_TARGET, 0)} ({tr_num((otif - OTIF_TARGET) * 100, 1)} puan)",
         GOOD if otif >= OTIF_TARGET else BAD),
    ]
    card_html = "".join(
        f'<div class="card" style="left:{16 + 211 * i}px;top:60px;width:192px;height:96px;--c:{c[3]}">'
        f'<div class="ct">{e(c[0])}</div><div class="cv">{e(c[1])}</div><div class="cr">{e(c[2])}</div></div>'
        for i, c in enumerate(cards))

    colors = {HYBRID: BLUE, PLANNER: ORANGE}
    p1_items = [(m[0], float(m[1]), colors.get(m[0], NEUTRAL), f"{pct(m[1])} · sapma {pct(m[2], 1, True)}")
                for m in d["models"]]
    p1 = hbar(p1_items, 580, 176, 0.6, 1.0, [0.6, 0.7, 0.8, 0.9, 1.0], lambda t: pct(t, 0), 110)
    p1_title = ("Hibrit model, planlamacıdan daha doğru" if hy[1] > ts[1] else "Model doğruluğu, planlama TS ile karşılaştırma")

    s = d["series"]
    p2 = line_chart(588, 176, [mlabel(r[0], False) + (f" {r[0].year % 100}" if r[0].month == 1 else "") for r in s],
                    [(BLUE, [float(r[1]) for r in s], False), (NEUTRAL, [float(r[2]) for r in s], True),
                     (ORANGE, [float(r[3]) for r in s], False)],
                    -(-max(float(r[k]) for r in s for k in (1, 2, 3)) * 1.05 // 2000) * 2000)

    def stock_color(v):
        return BAD if v < 0.5 else WARN if v > 3 else GOOD

    g = [(name, float(v), stock_color(float(v)), tr_num(float(v), 2)) for name, v in d["stock_groups"]]
    p3 = hbar(g, 580, 176, 0, 3.5, [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5], lambda t: tr_num(t, 1), 130,
              lines=[(0.5, "0,5", BAD), (3, "3", BAD)])
    crit, excess = d["stock_flags"].get("Kriti", 0), d["stock_flags"].get("Fazla", 0)

    sup = [(name, float(v), GOOD if float(v) >= OTIF_TARGET else BAD, pct(v)) for name, v in d["suppliers"]]
    p4 = hbar(sup, 588, 176, 0, 1.0, [0, 0.2, 0.4, 0.6, 0.8, 1.0], lambda t: pct(t, 0), 170,
              lines=[(OTIF_TARGET, f"Hedef {pct(OTIF_TARGET, 0)}", INK2)])
    none_hit = all(float(v) < OTIF_TARGET for _, v in d["suppliers"])
    p4_title = "Hiçbir tedarikçi %95 hedefini tutturamıyor" if none_hit else "Tedarikçi OTIF, hedef %95"

    def panel(x, y, title, sub, body, w):
        return (f'<div class="panel" style="left:{x}px;top:{y}px;width:{w}px;height:236px">'
                f'<div class="pt">{e(title)}</div><div class="ps">{sub}</div>{body}</div>')

    def legend(items):
        return " &nbsp; ".join(f'<span class="lg"><i style="background:{c}"></i>{e(t)}</span>' for c, t in items)

    panels = "".join([
        panel(16, 168, p1_title, f"Son {n_months} ay · {n_series} seri (ürün grubu × kanal) · 1 − WAPE · eksen %60'tan başlar",
              p1, 612),
        panel(644, 168, "Satış, bütçe ve planlama tahmini (adet / ay)",
              legend([(BLUE, "Satış"), (NEUTRAL, "Bütçe"), (ORANGE, "TS Lag-1")]), p2, 620),
        panel(16, 416, "Stok kaç aylık satışı karşılıyor", f"{lm} · kesikli çizgiler 0,5 ve 3 ay", p3, 612),
        panel(644, 416, p4_title, "OTIF, tüm dönem", p4, 620),
    ])
    minis = (f'<div class="mini" style="left:452px;top:420px;--c:{BAD}">Kritik <b>{crit}</b></div>'
             f'<div class="mini" style="left:544px;top:420px;--c:{WARN}">Fazla <b>{excess}</b></div>')

    dq = d["dq"]
    dq_cards = (f'<div class="dq" style="left:792px"><span>Mükerrer satır (son yükleme)</span>'
                f'<b>{dq.get("DUPLICATE", 0)}</b></div>'
                f'<div class="dq" style="left:1032px"><span>Tanımsız kanal (son yükleme)</span>'
                f'<b>{dq.get("UNKNOWN_CHANNEL", 0)}</b></div>')
    foot = ("Tüm veriler sentetiktir; şirket, marka ve tedarikçi adları kurgusaldır, gerçek kişi ve kuruluşlarla ilgisi yoktur. "
            "Tahmin doğruluğu ürün grubu × kanal düzeyinde ve lag-1'dir.")

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yönetici Özeti — Önizleme</title>
<style>
:root{{--ink:{INK};--ink2:{INK2};--grid:{GRID}}}
*{{box-sizing:border-box}}
body{{margin:0;background:#f1f0ec;color:var(--ink);font:13px "Segoe UI",system-ui,sans-serif}}
.note{{max-width:1280px;margin:0 auto;padding:10px 16px;color:var(--ink2);font-size:12px}}
#wrap{{position:relative;max-width:1280px;margin:0 auto;overflow:hidden}}
#c{{position:relative;width:1280px;height:720px;background:#fcfcfb}}
#c>*{{position:absolute}}
h1{{margin:0;font-size:22px;font-weight:600;left:16px;top:8px;line-height:36px}}
.date{{right:16px;top:8px;line-height:36px;color:var(--ink2);font-size:13px}}
.card,.panel,.mini,.dq{{background:#fff;border:1px solid var(--grid);border-radius:6px}}
.card{{padding:10px 12px;border-left:4px solid var(--c)}}
.ct{{font-size:11px;color:var(--ink2)}}
.cv{{font-size:28px;font-weight:600;line-height:38px}}
.cr{{font-size:11px;color:var(--c);font-weight:600}}
.panel{{padding:8px 12px}}
.pt{{font-size:15px;font-weight:600}}
.ps{{font-size:11px;color:var(--ink2);margin-bottom:2px;min-height:15px}}
.lg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}}
svg text{{font-family:inherit}}
.ax{{font-size:10px;fill:var(--ink2)}} .lb{{font-size:11px;fill:var(--ink)}}
.vl{{font-size:11px;fill:var(--ink);font-weight:600;paint-order:stroke;stroke:#fff;stroke-width:3px}}
.ref{{font-size:10px;font-weight:600}}
.mini{{width:84px;height:26px;padding:4px 8px;font-size:11px;border-color:var(--c);color:var(--c)}}
.mini b{{font-size:13px;margin-left:4px}}
.foot{{left:16px;top:664px;width:760px;height:48px;font-size:11px;color:var(--ink2);line-height:16px;padding-top:6px}}
.dq{{top:664px;width:232px;height:48px;padding:6px 10px;display:flex;justify-content:space-between;align-items:center}}
.dq span{{font-size:11px;color:var(--ink2);width:150px}} .dq b{{font-size:22px}}
</style></head><body>
<div class="note"><b>Önizleme.</b> Bu bir Power BI raporu değildir; <code>docs/powerbi_dashboard_spec.md</code>
belirtimine göre sayfanın nasıl görüneceğini gösteren statik bir görüntüdür
(<code>powerbi/build_preview.py</code> ile üretilir). Veriler sentetiktir.</div>
<div id="wrap"><div id="c">
<h1>Tedarik Zinciri Yönetici Özeti</h1>
<div class="date">Veri tarihi: {d["last_invoice"].day} {mlabel(d["last_invoice"])}</div>
{card_html}{panels}{minis}
<div class="foot">{e(foot)}</div>{dq_cards}
</div></div>
<script>
function fit(){{var c=document.getElementById('c'),w=document.getElementById('wrap').clientWidth,s=Math.min(1,w/1280);
c.style.transform='scale('+s+')';c.style.transformOrigin='top left';
document.getElementById('wrap').style.height=(720*s)+'px';}}
window.addEventListener('resize',fit);fit();
</script></body></html>
"""


def main() -> None:
    rp.load_env_file()
    OUT.write_text(build(fetch()), encoding="utf-8")
    print(f"Önizleme -> {OUT}")


if __name__ == "__main__":
    main()
