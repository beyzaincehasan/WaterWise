"""Keşifsel veri analizi: grafikler (outputs/figures) + özet istatistikler.

Ortalama hesaplarında yalnızca GÖZLENEN saatler/günler kullanılır; kesinti
dönemleri sıfır tüketim gibi davranıp ortalamaları aşağı çekmez. Zaman
serisi grafiklerinde kesintiler boşluk olarak görünür.
"""
from __future__ import annotations

import json

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config, plot_style as ps
from .data_preprocessing import PreprocessingResult, load_processed
from .feature_engineering import is_night_hour

FIG = config.FIGURES_DIR
DAY_NAMES_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def _hourly_with_local(hourly: pd.DataFrame) -> pd.DataFrame:
    h = hourly.copy()
    local = h["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    h["hour_local"] = local.dt.hour
    h["date_local"] = local.dt.tz_localize(None).dt.normalize()
    h["dow"] = local.dt.dayofweek
    h["month_local"] = local.dt.tz_localize(None).dt.to_period("M")
    h["night"] = is_night_hour(h["hour_local"])
    return h


def _full_days(h: pd.DataFrame) -> pd.DataFrame:
    d = h.groupby(["apartment", "date_local"]).agg(
        n=("observed", "size"), n_obs=("observed", "sum"),
        liters=("consumption_liters", "sum"), dow=("dow", "first"))
    d = d[d["n"] == d["n_obs"]].reset_index()
    return d


def run_eda(r: PreprocessingResult | None = None) -> dict:
    ps.apply()
    r = r or load_processed()
    rec = r.records
    h = _hourly_with_local(r.hourly)
    obs = h[h["observed"]]
    days = _full_days(h)
    S: dict = {}

    # ---------------------------------------------------------------- toplam
    S["total_m3"] = round(rec["value_liters"].sum() / 1000, 3)
    S["apartment_m3"] = round(rec.loc[~rec["is_shared_area"], "value_liters"].sum() / 1000, 3)
    S["shared_m3"] = round(rec.loc[rec["is_shared_area"], "value_liters"].sum() / 1000, 3)

    # 1) Günlük bina tüketimi (kesintiler boşluk)
    rec_local_day = rec["timestamp_utc"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).dt.normalize()
    daily = rec.groupby([rec_local_day, "is_shared_area"])["value_liters"].sum().unstack(fill_value=0)
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    covered = pd.Series(False, index=full_idx)
    obs_days = h.groupby("date_local")["observed"].mean()
    covered.loc[obs_days.index[obs_days > 0.5]] = True
    daily = daily.reindex(full_idx).fillna(0.0)
    daily.loc[~covered.to_numpy()] = np.nan
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(daily.index, daily.get(False, 0) / 1000, lw=1.0, label="Daireler", color=ps.SERIES[0])
    ax.plot(daily.index, daily.get(True, 0) / 1000, lw=1.0, label="Ortak alanlar", color=ps.SERIES[1])
    for _, o in r.outages[r.outages["gap_hours"] > 24].iterrows():
        ax.axvspan(pd.Timestamp(o["start_utc"]).tz_localize(None), pd.Timestamp(o["end_utc"]).tz_localize(None),
                   color=ps.GRID, alpha=0.8, lw=0)
    ax.set_title("Günlük toplam su tüketimi (gri alanlar: veri toplama kesintisi)")
    ax.set_ylabel("m³ / gün")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ps.save(fig, FIG / "01_daily_total_consumption.png")

    # 2) Daire bazlı günlük ortalama (tam gözlenen günler)
    apt_daily = days.groupby("apartment")["liters"].agg(["mean", "median", "count"]).sort_values("mean")
    S["apartment_daily_mean_liters"] = apt_daily["mean"].round(1).to_dict()
    S["apartment_daily_median_liters"] = apt_daily["median"].round(1).to_dict()
    fig, ax = plt.subplots(figsize=(9, 6.5))
    y = np.arange(len(apt_daily))
    ax.barh(y - 0.2, apt_daily["mean"], height=0.38, color=ps.SERIES[0], label="Ortalama")
    ax.barh(y + 0.2, apt_daily["median"], height=0.38, color=ps.SERIES[1], label="Medyan")
    ax.set_yticks(y, apt_daily.index)
    ax.set_xlabel("Litre / gün (yalnızca tam gözlenen günler)")
    ax.set_title("Daire bazlı günlük tüketim")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    ps.save(fig, FIG / "02_apartment_daily_consumption.png")

    # 3) Sensör bazlı tüketim (ilk 20)
    sens = rec.groupby(["sensor_id", "attached_to", "is_shared_area"])["value_liters"].sum().reset_index()
    sens = sens.sort_values("value_liters", ascending=False)
    S["n_sensors"] = int(len(sens))
    S["top10_sensor_share"] = round(sens["value_liters"].head(10).sum() / sens["value_liters"].sum(), 4)
    top = sens.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = [ps.SERIES[1] if s else ps.SERIES[0] for s in top["is_shared_area"]]
    ax.barh(top["sensor_id"] + " · " + top["attached_to"], top["value_liters"] / 1000, color=colors, height=0.7)
    ax.set_xlabel("Toplam tüketim (m³)")
    ax.set_title("En çok tüketim kaydeden 20 sensör (mavi: daire, turuncu: ortak alan)")
    ax.grid(axis="y", visible=False)
    ps.save(fig, FIG / "03_sensor_consumption_top20.png")

    # 4) Kullanım kategorileri (daire içi), sıcak/soğuk
    apt_rec = rec[~rec["is_shared_area"]]
    cat = apt_rec.groupby(["usage_category", "water_type"])["value_liters"].sum().unstack(fill_value=0)
    cat = cat.loc[cat.sum(axis=1).sort_values().index]
    S["category_share_apartments"] = (cat.sum(axis=1) / cat.values.sum()).round(4).to_dict()
    S["hot_water_share_apartments"] = round(cat["hot"].sum() / cat.values.sum(), 4)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(cat.index, cat["cold"] / 1000, color=ps.SERIES[0], label="Soğuk su", height=0.6)
    ax.barh(cat.index, cat["hot"] / 1000, left=cat["cold"] / 1000, color=ps.SERIES[1], label="Sıcak su",
            height=0.6, edgecolor=ps.SURFACE, linewidth=2)
    for i, (c, v) in enumerate(cat.sum(axis=1).items()):
        ax.text(v / 1000, i, f"  %{100 * v / cat.values.sum():.1f}", va="center", color=ps.INK_2)
    ax.set_xlabel("Toplam tüketim (m³) – yalnızca daireler")
    ax.set_title("Kullanım kategorilerine göre tüketim")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    ps.save(fig, FIG / "04_usage_category_consumption.png")

    # 5) Saatlik örüntü (yerel saat), hafta içi / hafta sonu
    obs = obs.assign(weekend=obs["dow"] >= 5)
    hp = obs.groupby(["weekend", "hour_local"])["consumption_liters"].mean().unstack(0)
    S["hourly_profile_weekday"] = hp[False].round(2).tolist()
    S["hourly_profile_weekend"] = hp[True].round(2).tolist()
    S["peak_hour_weekday"] = int(hp[False].idxmax())
    S["peak_hour_weekend"] = int(hp[True].idxmax())
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(hp.index, hp[False], marker="o", ms=4, label="Hafta içi")
    ax.plot(hp.index, hp[True], marker="o", ms=4, label="Hafta sonu")
    ax.axvspan(-0.5, config.NIGHT_END_HOUR - 0.5, color=ps.GRID, alpha=0.5, lw=0)
    ax.text(0, ax.get_ylim()[1] * 0.92, "gece", color=ps.MUTED)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("Yerel saat (Europe/Stockholm)")
    ax.set_ylabel("Ortalama L / daire-saat")
    ax.set_title("Saatlik tüketim örüntüsü (gözlenen saatler)")
    ax.legend()
    ps.save(fig, FIG / "05_hourly_pattern_weekday_weekend.png")

    # 6) Haftalık: haftanın günlerine göre günlük ortalama
    dw = days.groupby("dow")["liters"].mean()
    S["dow_daily_mean_liters"] = dw.round(1).tolist()
    wk = days.assign(we=days["dow"] >= 5).groupby("we")["liters"].mean()
    S["weekday_daily_mean"] = round(float(wk[False]), 1)
    S["weekend_daily_mean"] = round(float(wk[True]), 1)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar([DAY_NAMES_TR[i] for i in dw.index], dw.values,
           color=[ps.SERIES[1] if i >= 5 else ps.SERIES[0] for i in dw.index], width=0.65)
    for i, v in enumerate(dw.values):
        ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", color=ps.INK_2)
    ax.set_ylabel("Ortalama L / daire-gün")
    ax.set_title("Haftanın günlerine göre günlük tüketim (turuncu: hafta sonu)")
    ax.grid(axis="x", visible=False)
    ps.save(fig, FIG / "06_weekly_pattern.png")

    # 7) Aylık: gözlenen saat başına normalize edilmiş daire-gün ortalaması
    mon = obs.groupby("month_local")["consumption_liters"].mean() * 24
    mcov = h.groupby("month_local")["observed"].mean()
    S["monthly_mean_daily_liters"] = {str(k): round(float(v), 1) for k, v in mon.items()}
    S["monthly_coverage"] = {str(k): round(float(v), 3) for k, v in mcov.items()}
    fig, ax = plt.subplots(figsize=(11, 3.8))
    x = mon.index.to_timestamp()
    full = pd.period_range(mon.index.min(), mon.index.max(), freq="M")
    mon_full = mon.reindex(full)
    mon_full[mcov.reindex(full).fillna(0) < 0.2] = np.nan   # neredeyse hiç gözlem yok → boşluk
    ax.plot(full.to_timestamp(), mon_full.values, marker="o", ms=4)
    ax.set_ylabel("L / daire-gün")
    ax.set_title("Aylık ortalama günlük tüketim (gözlenen saatlere göre normalize; kapsama <%20 olan aylar boş)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ps.save(fig, FIG / "07_monthly_consumption.png")

    # 8) Gece tüketimi: daire bazlı gece saatlik ortalaması ve aktif saat oranı
    night = obs[obs["night"]]
    nstat = night.groupby("apartment")["consumption_liters"].agg(
        mean="mean", active=lambda s: (s > 0).mean()).sort_values("mean")
    S["night_mean_liters_per_hour_all"] = round(float(night["consumption_liters"].mean()), 3)
    S["night_active_hour_fraction_all"] = round(float((night["consumption_liters"] > 0).mean()), 4)
    S["night_share_of_apartment_consumption"] = round(
        float(night["consumption_liters"].sum() / obs["consumption_liters"].sum()), 4)
    S["night_mean_by_apartment"] = nstat["mean"].round(3).to_dict()
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(nstat.index, nstat["mean"], color=ps.SERIES[6], height=0.7)
    for i, (m, a) in enumerate(zip(nstat["mean"], nstat["active"])):
        ax.text(m, i, f"  aktif saat %{100 * a:.0f}", va="center", color=ps.INK_2, fontsize=8)
    ax.set_xlabel("Gece (00–06 yerel) ortalama L / saat")
    ax.set_title("Daire bazlı gece tüketimi")
    ax.grid(axis="y", visible=False)
    ps.save(fig, FIG / "08_night_consumption_by_apartment.png")

    # 9) Dağılım ve aykırı değerler
    pos = obs.loc[obs["consumption_liters"] > 0, "consumption_liters"]
    S["hourly_zero_fraction"] = round(float((obs["consumption_liters"] == 0).mean()), 4)
    S["hourly_positive_quantiles"] = {q: round(float(pos.quantile(q)), 1) for q in [0.5, 0.9, 0.95, 0.99, 0.999]}
    S["hourly_max_liters"] = round(float(pos.max()), 1)
    q1, q3 = pos.quantile([0.25, 0.75])
    S["hourly_iqr_outlier_fraction"] = round(float((pos > q3 + 1.5 * (q3 - q1)).mean()), 4)
    S["record_high_rate_by_fixture"] = rec.loc[rec["high_rate_flag"], "attached_to"].value_counts().to_dict()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    bins = np.logspace(0, np.log10(pos.max() + 1), 60)
    axes[0].hist(pos, bins=bins, color=ps.SERIES[0])
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Saatlik tüketim (L, log ölçek; yalnızca >0)")
    axes[0].set_ylabel("Saat sayısı (log)")
    axes[0].set_title("Saatlik daire tüketimi dağılımı")
    for q, ls in [(0.99, "--"), (0.999, ":")]:
        v = pos.quantile(q)
        axes[0].axvline(v, color=ps.INK_2, ls=ls, lw=1)
        axes[0].text(v, axes[0].get_ylim()[1] * 0.3, f" p{q * 100:g}={v:.0f} L", color=ps.INK_2, fontsize=8)
    vals = rec["value_liters"]
    axes[1].hist(vals, bins=np.logspace(0, np.log10(301), 50), color=ps.SERIES[2])
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].axvline(100, color=ps.INK_2, ls="--", lw=1)
    axes[1].text(100, axes[1].get_ylim()[1] * 0.3, " 100 L / 10 dk", color=ps.INK_2, fontsize=8)
    axes[1].set_xlabel("Tek kayıt değeri (L / 10 dk, log ölçek)")
    axes[1].set_title("Sensör kayıt değerleri dağılımı")
    ps.save(fig, FIG / "09_consumption_distribution_outliers.png")

    # 10) Veri kapsama: daire × ay
    cov = h.groupby(["apartment", "month_local"])["observed"].mean().unstack()
    S["overall_apartment_hour_coverage"] = round(float(h["observed"].mean()), 4)
    fig, ax = plt.subplots(figsize=(12, 6.5))
    im = ax.imshow(cov.values, aspect="auto", cmap=ps.SEQ_CMAP, vmin=0, vmax=1, interpolation="nearest")
    ax.set_yticks(range(len(cov.index)), cov.index, fontsize=7.5)
    xt = list(range(0, len(cov.columns), 3))
    ax.set_xticks(xt, [str(cov.columns[i]) for i in xt], rotation=45, ha="right", fontsize=8)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025)
    cb.set_label("Gözlenen saat oranı", color=ps.INK_2)
    ax.set_title("Veri kapsama oranı (daire × ay)")
    ps.save(fig, FIG / "10_data_coverage_heatmap.png")

    # 11) Eksik zaman aralıkları: bina geneli kesinti süreleri
    og = r.outages.sort_values("start_utc")
    S["building_outages"] = [
        {"start_utc": str(a), "end_utc": str(b), "hours": round(float(g), 1)}
        for a, b, g in zip(og["start_utc"], og["end_utc"], og["gap_hours"])]
    fig, ax = plt.subplots(figsize=(10, 3.8))
    lab = pd.to_datetime(og["start_utc"]).dt.strftime("%Y-%m-%d")
    ax.bar(range(len(og)), og["gap_hours"] / 24, color=ps.SERIES[1], width=0.65)
    ax.set_xticks(range(len(og)), lab, rotation=45, ha="right", fontsize=8)
    ax.set_yscale("log")
    ax.set_ylabel("Süre (gün, log)")
    ax.set_title(f"Bina geneli veri toplama kesintileri (> {config.BUILDING_OUTAGE_HOURS:g} saat kayıtsız)")
    ax.grid(axis="x", visible=False)
    ps.save(fig, FIG / "11_building_outages.png")

    # 12) Gözlem süreleri
    span = h.groupby("apartment").agg(first=("hour_utc", "min"), last=("hour_utc", "max"),
                                     obs_hours=("observed", "sum"), total=("observed", "size"))
    span["obs_days"] = span["obs_hours"] / 24
    span["span_days"] = span["total"] / 24
    S["apartment_observed_days"] = span["obs_days"].round(1).to_dict()
    S["apartment_span_days"] = span["span_days"].round(1).to_dict()
    sp = span.sort_values("obs_days")
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(sp.index, sp["span_days"], color=ps.GRID, height=0.7, label="İzleme penceresi")
    ax.barh(sp.index, sp["obs_days"], color=ps.SERIES[0], height=0.7, label="Gözlenen süre")
    ax.set_xlabel("Gün")
    ax.set_title("Dairelerin gözlem süreleri")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    ps.save(fig, FIG / "12_apartment_observation_periods.png")

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.REPORTS_DIR / "eda_summary.json", "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, indent=2, default=str)
    return S


if __name__ == "__main__":
    s = run_eda()
    print(json.dumps({k: v for k, v in s.items() if not isinstance(v, (dict, list))}, ensure_ascii=False, indent=1))
