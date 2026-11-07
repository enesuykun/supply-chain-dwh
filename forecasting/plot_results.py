from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from forecast_model import load_sales

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
IMG = ROOT / "docs" / "img"

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, S2 = "#2a78d6", "#eb6834"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})


def style(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x" if ax.get_ylabel() == "" else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def model_comparison():
    df = pd.read_csv(OUT / "model_comparison.csv").sort_values("accuracy_1_minus_wape")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bars = ax.barh(df["model"], df["accuracy_1_minus_wape"] * 100, color=S1, height=0.55)
    for b, acc, bias in zip(bars, df["accuracy_1_minus_wape"], df["bias"]):
        ax.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2,
                f"%{acc * 100:.1f}   (bias {bias * 100:+.1f}%)", va="center", color=INK, fontsize=9)
    ax.set_xlim(60, 100)
    ax.set_xlabel("Tahmin doğruluğu (1 − WAPE), %")
    ax.tick_params(axis="y", length=0)
    style(ax)
    ax.set_title("Lag-1 tahmin doğruluğu — son 6 ay backtest (ürün grubu × kanal)",
                 loc="left", color=INK, fontsize=11, pad=12)
    fig.tight_layout()
    fig.savefig(IMG / "model_comparison.png", dpi=160)
    plt.close(fig)


def example_series(group="Elektrikli Termosifon", channel="BAY"):
    s = load_sales()
    s = s[(s["channel_code"] == channel) & (s["product_group"] == group)]
    act = s.groupby("month")["qty"].sum()
    fc = pd.read_csv(OUT / "ml_forecast.csv", parse_dates=["target_month"])
    fc = fc[(fc["product_group"] == group) & (fc["channel_code"] == channel)]
    model = fc["model_name"].iloc[0]

    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(act.index, act.values, color=S1, linewidth=2, label="Gerçekleşen")
    xs = [act.index[-1], *fc["target_month"]]
    ys = [act.values[-1], *fc["forecast_qty"]]
    ax.plot(xs, ys, color=S2, linewidth=2, linestyle=(0, (4, 3)), label=f"Tahmin ({model})")
    ax.plot(fc["target_month"], fc["forecast_qty"], "o", color=S2, markersize=5,
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.text(act.index[-1], act.values[-1], "  Eyl 2026", color=INK2, fontsize=8, va="bottom")
    ax.set_ylabel("Adet / ay")
    ax.set_ylim(bottom=0)
    style(ax)
    ax.legend(frameon=False, loc="upper left", ncol=2, labelcolor=INK)
    ax.set_title(f"{group} · Bayi kanalı — 5 aylık projeksiyon", loc="left", color=INK, fontsize=11, pad=12)
    fig.tight_layout()
    fig.savefig(IMG / "example_forecast.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    IMG.mkdir(parents=True, exist_ok=True)
    model_comparison()
    example_series()
    print(f"Görseller -> {IMG}")
