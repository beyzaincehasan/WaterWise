"""Model değerlendirme: gerçek veride alarm oranları + sentetik anomali yakalama.

Değerlendirme protokolü
-----------------------
* Eşikler ve tasarım kararları (global/daire bazlı model, hiperparametre
  karşılaştırması) YALNIZCA doğrulama dönemi + doğrulama sentetik olaylarıyla
  verilir.
* Test dönemi (2022-07 – 2023-01) ve test sentetik olayları (farklı tohum) en
  sonda, sabitlenmiş model ve eşiklerle bir kez raporlanır.
* Gerçek veride doğrulanmış "normal" etiketi yoktur; gerçek saatlerdeki alarm
  oranı kesin yanlış pozitif oranı DEĞİL, onun üst sınırına yakın bir
  yaklaşık değerdir (gerçek anomaliler de içerebilir).
* Bir sentetik olay, olay saatlerinden en az birinin durumu eşik üstündeyse
  "yakalandı" sayılır (olay bazlı). Saat bazlı oranlar da raporlanır.
"""
from __future__ import annotations

import json
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config, plot_style as ps
from .data_preprocessing import load_processed
from .feature_engineering import FEATURE_COLUMNS, compute_features, slots_to_hourly
from .normal_profile import get_profile, load_profiles
from .predict import WaterWiseAnomalyDetector
from .synthetic_anomalies import SCENARIOS, STRESS_SCENARIOS, generate_events, inject, save_events
from .train_model import (anomaly_scores, calibrate_apartment_thresholds, calibrate_thresholds,
                          fit_isolation_forest, split_periods)

N_EVENTS_PER_SCENARIO = 300
SEED_VALID = 101
SEED_TEST = 202
SEED_STRESS = 303
SCEN_TR = {
    "S1_night_continuous_flow": "S1 Gece sürekli akış",
    "S2_high_consumption": "S2 Olağandışı yüksek tüketim",
    "S3_unusual_hour": "S3 Alışılmadık saat",
    "S4_short_spike": "S4 Kısa süreli artış",
}


# ---------------------------------------------------------------------------
# Sentetik olay özellikleri
# ---------------------------------------------------------------------------
def compute_event_features(events, slots: pd.DataFrame, profiles: dict) -> pd.DataFrame:
    """Her olay için: geçmiş pencere + olay → enjekte et → özellik; olay saatlerini döndür."""
    by_apt = {a: g.drop(columns="apartment").reset_index(drop=True) for a, g in slots.groupby("apartment")}
    rows = []
    pad = pd.Timedelta(days=config.HISTORY_DAYS + 1)
    for ev in events:
        s = by_apt[ev.apartment]
        lo = (ev.start_utc - pad).floor("h")
        hi = ev.end_utc.floor("h") + pd.Timedelta(minutes=50)
        w = s[(s["slot_utc"] >= lo) & (s["slot_utc"] <= hi)][["slot_utc", "liters", "observed"]]
        w = inject(w.reset_index(drop=True), ev)
        prof, _ = get_profile(profiles, ev.apartment)
        f = compute_features(slots_to_hourly(w), prof)
        f = f[f["hour_utc"].isin(ev.hours_utc())].copy()
        f.insert(0, "event_id", ev.event_id)
        f.insert(1, "scenario", ev.scenario)
        f.insert(2, "apartment", ev.apartment)
        f["event_total_liters"] = ev.total_liters
        f["event_params"] = json.dumps(ev.params)
        rows.append(f)
    return pd.concat(rows, ignore_index=True)


def _thr_arrays(thr, n: int) -> tuple[np.ndarray, np.ndarray]:
    """`thr`: global eşik sözlüğü veya (şüpheli_dizisi, anormal_dizisi) satır bazlı eşikler."""
    if isinstance(thr, dict):
        return np.full(n, thr["suspicious"]), np.full(n, thr["anomalous"])
    return np.asarray(thr[0], dtype=float), np.asarray(thr[1], dtype=float)


def row_thresholds(det: WaterWiseAnomalyDetector, apartments) -> tuple[np.ndarray, np.ndarray]:
    """Her satır için dedektörün kullandığı (daireye uyarlanmış veya global) eşikler."""
    apartments = pd.Series(apartments).to_numpy()
    uniq = {a: det.thresholds_for(a)[0] for a in pd.unique(apartments)}
    return (np.array([uniq[a]["suspicious"] for a in apartments]),
            np.array([uniq[a]["anomalous"] for a in apartments]))


def summarize_events(ev_feats: pd.DataFrame, scores: np.ndarray, thr) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Olay bazlı (max skor) ve senaryo bazlı yakalama oranları."""
    susp, anom = _thr_arrays(thr, len(ev_feats))
    d = ev_feats[["event_id", "scenario", "apartment", "event_total_liters", "event_params",
                  "consumption_liters", "hour_local", "active_slots", "continuous_activity_min"]].copy()
    d["score"] = scores
    d["flag_susp"] = d["score"].to_numpy() >= susp
    d["flag_anom"] = d["score"].to_numpy() >= anom
    ev = d.groupby("event_id").agg(
        scenario=("scenario", "first"), apartment=("apartment", "first"),
        total_liters=("event_total_liters", "first"), params=("event_params", "first"),
        max_score=("score", "max"), detected=("flag_susp", "any"), detected_anomalous=("flag_anom", "any"),
        hour_detect_rate=("flag_susp", "mean"), n_hours=("score", "size")).reset_index()
    sc = ev.groupby("scenario").agg(
        n_events=("event_id", "size"),
        detection_rate=("detected", "mean"),
        detection_rate_anomalous=("detected_anomalous", "mean"),
        hour_level_detection=("hour_detect_rate", "mean"),
        median_max_score=("max_score", "median")).reset_index()
    return ev, sc


def real_alarm_stats(df: pd.DataFrame, scores: np.ndarray, thr) -> dict:
    s = np.asarray(scores)
    susp, anom_t = _thr_arrays(thr, len(s))
    local = df["hour_utc"].dt.tz_convert(config.LOCAL_TZ)
    day = pd.Series(local.dt.date.to_numpy(), index=df.index)
    flag = pd.Series(s >= susp, index=df.index)
    anom = pd.Series(s >= anom_t, index=df.index)
    by_day = pd.DataFrame({"apt": df["apartment"], "day": day, "f": flag, "a": anom}).groupby(["apt", "day"])
    night = df["is_night"].to_numpy() == 1
    return {
        "n_hours": int(len(s)),
        "hour_alarm_rate_suspicious_or_higher": float(flag.mean()),
        "hour_alarm_rate_anomalous": float(anom.mean()),
        "night_hour_alarm_rate": float(flag[night].mean()) if night.any() else None,
        "apartment_day_alarm_rate": float(by_day["f"].any().mean()),
        "apartment_day_anomalous_rate": float(by_day["a"].any().mean()),
        "n_apartment_days": int(by_day.ngroups),
    }


# ---------------------------------------------------------------------------
# Ana değerlendirme
# ---------------------------------------------------------------------------
def run_evaluation(n_events: int = N_EVENTS_PER_SCENARIO) -> dict:
    t0 = time.time()
    ps.apply()
    pre = load_processed()
    det = WaterWiseAnomalyDetector()
    profiles = load_profiles()
    feats = pd.read_parquet(config.PROCESSED_DIR / "apartment_hourly_features.parquet")
    parts = split_periods(feats)
    th = det.thresholds                     # global eşikler
    R: dict = {"thresholds": th, "apartment_thresholds": det.apartment_thresholds,
               "threshold_policy": "final: global model + daireye uyarlanmış (yalnızca yukarı yönlü) eşikler"}
    TA = {k: row_thresholds(det, v["apartment"]) for k, v in parts.items()}

    # Gerçek veri
    sc_val = det.score(parts["valid"][FEATURE_COLUMNS])
    sc_test = det.score(parts["test"][FEATURE_COLUMNS])
    sc_train = det.score(parts["train"][FEATURE_COLUMNS])
    R["real_validation"] = real_alarm_stats(parts["valid"], sc_val, TA["valid"])
    R["real_test"] = real_alarm_stats(parts["test"], sc_test, TA["test"])
    R["real_train"] = real_alarm_stats(parts["train"], sc_train, TA["train"])
    # Şeffaflık: ilk sürüm (yalnızca global eşik) sonuçları
    R["global_threshold_only"] = {
        "real_validation": real_alarm_stats(parts["valid"], sc_val, th),
        "real_test": real_alarm_stats(parts["test"], sc_test, th),
    }

    # "Seçilmiş normal" test alt kümesi: tek kayıtta >=100 L/10 dk (olası gerçek
    # anomali veya toplu gönderim) içeren saatler hariç
    rec = pre.apartment_records
    hr = rec.loc[rec["high_rate_flag"]].assign(hour_utc=lambda d: d["timestamp_utc"].dt.floor("h"))
    hr_keys = set(zip(hr["apartment"], hr["hour_utc"]))
    t = parts["test"]
    sel = ~pd.Series([(a, h) in hr_keys for a, h in zip(t["apartment"], t["hour_utc"])], index=t.index)
    m = sel.to_numpy()
    R["real_test_selected_normal"] = real_alarm_stats(t[sel], sc_test[m], (TA["test"][0][m], TA["test"][1][m]))
    R["real_test_selected_normal"]["excluded_hours"] = int((~sel).sum())

    # Sentetik olaylar
    ev_val = generate_events(pre.hourly, profiles, config.VALID_START, config.VALID_END, n_events, SEED_VALID, "VAL")
    ev_test = generate_events(pre.hourly, profiles, config.TEST_START, config.TEST_END, n_events, SEED_TEST, "TEST")
    save_events(ev_val, "validation")
    save_events(ev_test, "test")
    ef_val = compute_event_features(ev_val, pre.slots, profiles)
    ef_test = compute_event_features(ev_test, pre.slots, profiles)
    ef_val.to_parquet(config.SYNTHETIC_DIR / "validation_event_features.parquet", index=False)
    ef_test.to_parquet(config.SYNTHETIC_DIR / "test_event_features.parquet", index=False)
    assert ef_val[FEATURE_COLUMNS].notna().all().all() and ef_test[FEATURE_COLUMNS].notna().all().all()

    es_val = det.score(ef_val[FEATURE_COLUMNS])
    es_test = det.score(ef_test[FEATURE_COLUMNS])
    TE_val = row_thresholds(det, ef_val["apartment"])
    TE_test = row_thresholds(det, ef_test["apartment"])
    evv, scv = summarize_events(ef_val, es_val, TE_val)
    evt, sct = summarize_events(ef_test, es_test, TE_test)
    R["synthetic_validation"] = scv.to_dict(orient="records")
    R["synthetic_test"] = sct.to_dict(orient="records")
    R["global_threshold_only"]["synthetic_validation"] = summarize_events(ef_val, es_val, th)[1].to_dict(orient="records")
    R["global_threshold_only"]["synthetic_test"] = summarize_events(ef_test, es_test, th)[1].to_dict(orient="records")

    # Olay saatleri zaten (enjeksiyon olmadan) alarm veriyor muydu?
    key = ["apartment", "hour_utc"]
    clean = feats.set_index(key)
    base = ef_test[key].join(clean[FEATURE_COLUMNS], on=key)
    base_sc = det.score(base[FEATURE_COLUMNS])
    bflag = pd.DataFrame({"event_id": ef_test["event_id"], "f": base_sc >= TE_test[0]}) \
        .groupby("event_id")["f"].any()
    evt["clean_window_already_flagged"] = evt["event_id"].map(bflag)
    R["synthetic_test_clean_window_flag_rate"] = (
        evt.groupby("scenario")["clean_window_already_flagged"].mean().to_dict())

    # Yanlış negatifler (test)
    fn = evt[~evt["detected"]].sort_values("max_score")
    fn.to_csv(config.ANOMALIES_DIR / "synthetic_test_false_negatives.csv", index=False)
    evt.to_csv(config.ANOMALIES_DIR / "synthetic_test_event_results.csv", index=False)
    evv.to_csv(config.ANOMALIES_DIR / "synthetic_validation_event_results.csv", index=False)
    R["false_negative_examples"] = fn.head(10)[["event_id", "scenario", "apartment", "total_liters",
                                                "params", "max_score"]].to_dict(orient="records")
    # S1 yakalama oranı – debiye göre
    s1 = evt[evt["scenario"] == "S1_night_continuous_flow"].copy()
    s1["rate"] = s1["params"].map(lambda p: json.loads(p)["rate_l_per_hour"])
    s1["rate_bin"] = pd.cut(s1["rate"], [6, 10, 15, 20, 25, 30], include_lowest=True)
    R["s1_detection_by_rate_test"] = {str(k): float(v) for k, v in
                                      s1.groupby("rate_bin", observed=True)["detected"].mean().items()}

    # Stres testi: sayaç çözünürlüğünün altındaki düşük debili gece sızıntıları (test dönemi)
    ev_st = generate_events(pre.hourly, profiles, config.TEST_START, config.TEST_END, n_events, SEED_STRESS,
                            "STRESS", scenarios=list(STRESS_SCENARIOS))
    save_events(ev_st, "stress_test")
    ef_st = compute_event_features(ev_st, pre.slots, profiles)
    est, _ = summarize_events(ef_st, det.score(ef_st[FEATURE_COLUMNS]), row_thresholds(det, ef_st["apartment"]))
    est["rate"] = est["params"].map(lambda p: json.loads(p)["rate_l_per_hour"])
    est["rate_bin"] = pd.cut(est["rate"], [1, 2, 3, 4, 5, 6], include_lowest=True)
    est.to_csv(config.ANOMALIES_DIR / "stress_low_rate_event_results.csv", index=False)
    R["stress_low_rate_test"] = {
        "n_events": int(len(est)),
        "detection_rate": float(est["detected"].mean()),
        "detection_rate_anomalous": float(est["detected_anomalous"].mean()),
        "by_rate_l_per_hour": {str(k): float(v) for k, v in
                               est.groupby("rate_bin", observed=True)["detected"].mean().items()},
    }

    # Eşik taraması – GLOBAL eşik (doğrulama yüzdeliklerinden); sonuçlar test üzerinde
    sweep = []
    for q in [0.90, 0.93, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999]:
        thr = float(np.quantile(sc_val, q))
        row = {"valid_quantile": q, "threshold": thr,
               "test_real_hour_alarm_rate": float((sc_test >= thr).mean()),
               "valid_real_hour_alarm_rate": float((sc_val >= thr).mean())}
        tmp = pd.DataFrame({"event_id": ef_test["event_id"], "scenario": ef_test["scenario"], "f": es_test >= thr})
        det_rate = tmp.groupby(["scenario", "event_id"])["f"].any().groupby("scenario").mean()
        for s_, v in det_rate.items():
            row[f"test_detect_{s_[:2]}"] = float(v)
        sweep.append(row)
    sweep_df = pd.DataFrame(sweep)
    sweep_df.to_csv(config.REPORTS_DIR / "threshold_sweep.csv", index=False)
    R["threshold_sweep"] = sweep_df.to_dict(orient="records")

    # Daire bazlı davranış (test)
    pt = parts["test"].assign(score=sc_test, flag=sc_test >= TA["test"][0], flag_g=sc_test >= th["suspicious"])
    apt = pt.groupby("apartment").agg(hours=("score", "size"), alarm_rate=("flag", "mean"),
                                      alarm_rate_global_threshold=("flag_g", "mean"),
                                      median_score=("score", "median"))
    apt["threshold_raised"] = apt.index.map(lambda a: det.apartment_thresholds.get(a, {}).get("raised", False))
    apt["s1_detection"] = s1.groupby("apartment")["detected"].mean()
    apt["synthetic_detection_all"] = evt.groupby("apartment")["detected"].mean()
    apt.to_csv(config.REPORTS_DIR / "per_apartment_test_behavior.csv")
    R["per_apartment_test"] = apt.round(4).reset_index().to_dict(orient="records")

    # Global vs daire bazlı model (karar: doğrulama; bilgi amaçlı test)
    R["model_scope_comparison"] = compare_model_scope(parts, ef_val, ef_test)
    # Hiperparametre duyarlılığı (yalnızca doğrulama)
    R["hyperparameter_study_validation"] = hyperparameter_study(parts, ef_val)

    # Gerçek test anomalileri (en yüksek skorlar) – açıklamalarıyla
    R["real_test_top_anomalies_file"] = export_real_anomalies(det, parts["test"], sc_test, profiles)

    make_figures(sc_val, sc_test, es_test, ef_test, evt, sweep_df, apt, th, pre, det, profiles, ev_test)
    R["runtime_seconds"] = round(time.time() - t0, 1)
    with open(config.REPORTS_DIR / "evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2, default=str)
    write_tables(R)
    return R


def compare_model_scope(parts: dict, ef_val: pd.DataFrame, ef_test: pd.DataFrame) -> dict:
    """Global model vs her daire için ayrı Isolation Forest."""
    out = {}
    tr, va, te = parts["train"], parts["valid"], parts["test"]
    g = fit_isolation_forest(tr[FEATURE_COLUMNS])
    gth = calibrate_thresholds(anomaly_scores(g, va[FEATURE_COLUMNS]))
    gath = calibrate_apartment_thresholds(va, anomaly_scores(g, va[FEATURE_COLUMNS]), gth)

    def arr(apts):
        a = pd.Series(apts).to_numpy()
        return (np.array([gath.get(x, gth)["suspicious"] for x in a]),
                np.array([gath.get(x, gth)["anomalous"] for x in a]))
    results = {"global": {}, "global_adaptive_threshold": {}, "per_apartment": {}}
    for name, ef, real in [("validation", ef_val, va), ("test", ef_test, te)]:
        s = anomaly_scores(g, ef[FEATURE_COLUMNS])
        rs = anomaly_scores(g, real[FEATURE_COLUMNS])
        for key, thr_ev, thr_real in [("global", gth, gth),
                                      ("global_adaptive_threshold", arr(ef["apartment"]), arr(real["apartment"]))]:
            _, sc = summarize_events(ef, s, thr_ev)
            f = rs >= _thr_arrays(thr_real, len(rs))[0]
            apt_rates = pd.Series(f).groupby(real["apartment"].to_numpy()).mean()
            results[key][name] = {
                "detection": dict(zip(sc["scenario"], sc["detection_rate"].round(4))),
                "real_hour_alarm_rate": float(f.mean()),
                "alarm_rate_std_across_apartments": float(apt_rates.std()),
                "max_apartment_alarm_rate": float(apt_rates.max()),
                "n_apartments_alarm_gt_10pct": int((apt_rates > 0.10).sum()),
            }
    # Daire bazlı
    models, ths = {}, {}
    for apt, grp in tr.groupby("apartment"):
        m = fit_isolation_forest(grp[FEATURE_COLUMNS])
        vs = va[va["apartment"] == apt]
        if len(vs) < 200:
            continue
        models[apt] = m
        ths[apt] = calibrate_thresholds(anomaly_scores(m, vs[FEATURE_COLUMNS]))
    for name, ef, real in [("validation", ef_val, va), ("test", ef_test, te)]:
        s = np.full(len(ef), np.nan)
        susp = np.full(len(ef), np.nan)
        for apt, idx in ef.groupby("apartment").groups.items():
            if apt in models:
                pos = ef.index.get_indexer(idx)
                s[pos] = anomaly_scores(models[apt], ef.loc[idx, FEATURE_COLUMNS])
                susp[pos] = ths[apt]["suspicious"]
        keep = ~np.isnan(s)
        d = ef.loc[keep, ["event_id", "scenario"]].assign(f=s[keep] >= susp[keep])
        det_rate = d.groupby(["scenario", "event_id"])["f"].any().groupby("scenario").mean()
        alarms, per_apt = [], {}
        for apt, grp in real.groupby("apartment"):
            if apt in models:
                f = anomaly_scores(models[apt], grp[FEATURE_COLUMNS]) >= ths[apt]["suspicious"]
                alarms.append(f)
                per_apt[apt] = f.mean()
        results["per_apartment"][name] = {
            "detection": {k: round(float(v), 4) for k, v in det_rate.items()},
            "real_hour_alarm_rate": float(np.concatenate(alarms).mean()),
            "alarm_rate_std_across_apartments": float(pd.Series(per_apt).std()),
            "max_apartment_alarm_rate": float(pd.Series(per_apt).max()),
            "n_apartments_alarm_gt_10pct": int((pd.Series(per_apt) > 0.10).sum()),
            "n_models": len(models),
            "min_train_rows_per_apartment": int(tr.groupby("apartment").size().min()),
        }
    out.update(results)
    return out


def hyperparameter_study(parts: dict, ef_val: pd.DataFrame) -> list[dict]:
    """Küçük ızgara; eşikler her konfigürasyon için doğrulama yüzdeliğinden. Yalnızca doğrulama."""
    rows = []
    for n_est in [100, 300]:
        for ms in [256, 512, 2048]:
            m = fit_isolation_forest(parts["train"][FEATURE_COLUMNS], {"n_estimators": n_est, "max_samples": ms})
            vs = anomaly_scores(m, parts["valid"][FEATURE_COLUMNS])
            th = calibrate_thresholds(vs)
            _, sc = summarize_events(ef_val, anomaly_scores(m, ef_val[FEATURE_COLUMNS]), th)
            r = {"n_estimators": n_est, "max_samples": ms}
            r.update({f"valid_detect_{k[:2]}": round(float(v), 4) for k, v in zip(sc["scenario"], sc["detection_rate"])})
            r["valid_detect_mean"] = round(float(sc["detection_rate"].mean()), 4)
            rows.append(r)
    return rows


def export_real_anomalies(det: WaterWiseAnomalyDetector, test: pd.DataFrame, scores: np.ndarray,
                          profiles: dict) -> str:
    status = np.empty(len(scores), dtype=object)
    for apt, idx in pd.Series(range(len(scores))).groupby(test["apartment"].to_numpy()):
        status[idx.to_numpy()] = det.classify(scores[idx.to_numpy()], apt)
    d = test.assign(anomaly_score=scores, status=status)
    d = d[d["status"] != config.STATUS_NORMAL].sort_values("anomaly_score", ascending=False)
    rows = []
    for _, r in d.iterrows():
        prof, spec = get_profile(profiles, r["apartment"])
        reasons = det.explain(r, prof, spec)
        rows.append({
            "apartment": r["apartment"],
            "hour_utc": r["hour_utc"].isoformat(),
            "hour_local": r["hour_utc"].tz_convert(config.LOCAL_TZ).isoformat(),
            "consumption_liters": r["consumption_liters"],
            "active_slots": r["active_slots"],
            "continuous_activity_min": r["continuous_activity_min"],
            "historical_same_hour_mean": round(r["historical_same_hour_mean"], 2),
            "anomaly_score": round(r["anomaly_score"], 4),
            "status": r["status"],
            "reason_codes": ";".join(x["code"] for x in reasons),
            "message": det.compose_message(r["status"], reasons),
        })
    out = config.ANOMALIES_DIR / "real_test_alarms.csv"
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    return str(out.relative_to(config.PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Grafikler ve tablolar
# ---------------------------------------------------------------------------
def make_figures(sc_val, sc_test, es_test, ef_test, evt, sweep, apt, th, pre, det, profiles, ev_test) -> None:
    F = config.FIGURES_DIR
    # 13) Skor dağılımı: gerçek test saatleri vs sentetik olay max skorları
    fig, ax = plt.subplots(figsize=(10, 4.2))
    bins = np.linspace(0.3, 0.85, 70)
    ax.hist(sc_test, bins=bins, density=True, color=ps.GRID, edgecolor=ps.AXIS, lw=0.4,
            label="Gerçek test saatleri")
    for i, (s, lab) in enumerate(SCEN_TR.items()):
        v = evt.loc[evt["scenario"] == s, "max_score"]
        ax.hist(v, bins=bins, density=True, histtype="step", lw=2, color=ps.SERIES[i], label=f"{lab} (olay max)")
    ax.axvline(th["suspicious"], color=ps.INK_2, ls="--", lw=1)
    ax.axvline(th["anomalous"], color=ps.INK, ls="-", lw=1)
    ax.text(th["suspicious"], ax.get_ylim()[1] * 0.95, " Şüpheli eşiği", color=ps.INK_2, fontsize=8)
    ax.text(th["anomalous"], ax.get_ylim()[1] * 0.85, " Anormal eşiği", color=ps.INK, fontsize=8)
    ax.set_xlabel("Anomali skoru (Liu vd. s(x); yüksek = daha olağandışı, olasılık değildir)")
    ax.set_ylabel("Yoğunluk")
    ax.set_title("Anomali skoru dağılımı – test dönemi")
    ax.legend(fontsize=8, loc="upper left")
    ps.save(fig, F / "13_anomaly_score_distribution.png")

    # 14) Senaryo bazlı yakalama oranı
    sc = evt.groupby("scenario").agg(susp=("detected", "mean"), anom=("detected_anomalous", "mean"))
    fig, ax = plt.subplots(figsize=(9, 3.8))
    y = np.arange(len(sc))
    ax.barh(y - 0.2, sc["susp"] * 100, height=0.38, color=ps.SERIES[0], label="≥ Şüpheli")
    ax.barh(y + 0.2, sc["anom"] * 100, height=0.38, color=ps.SERIES[1], label="Anormal")
    for i, (a, b) in enumerate(zip(sc["susp"], sc["anom"])):
        ax.text(a * 100, i - 0.2, f" %{a * 100:.1f}", va="center", color=ps.INK_2, fontsize=8)
        ax.text(b * 100, i + 0.2, f" %{b * 100:.1f}", va="center", color=ps.INK_2, fontsize=8)
    ax.axvline(90, color=ps.INK_2, ls=":", lw=1)
    ax.text(90, len(sc) - 0.45, "hedef %90", color=ps.INK_2, fontsize=8, ha="right")
    ax.set_yticks(y, [SCEN_TR[s] for s in sc.index])
    ax.set_xlim(0, 112)
    ax.set_xlabel("Olay yakalama oranı (%) – test dönemi sentetik olaylar")
    ax.set_title("Senaryo bazlı sentetik anomali yakalama")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", visible=False)
    ps.save(fig, F / "14_synthetic_detection_by_scenario.png")

    # 15) Eşik etkisi
    fig, ax = plt.subplots(figsize=(9, 4))
    x = sweep["test_real_hour_alarm_rate"] * 100
    for i, s in enumerate(SCEN_TR):
        c = f"test_detect_{s[:2]}"
        ax.plot(x, sweep[c] * 100, marker="o", ms=5, color=ps.SERIES[i], label=SCEN_TR[s])
    for _, r in sweep.iterrows():
        ax.annotate(f"q={r['valid_quantile']:g}", (r["test_real_hour_alarm_rate"] * 100, 2),
                    fontsize=7, color=ps.MUTED, rotation=90, ha="center")
    ax.axvline(10, color=ps.INK_2, ls=":", lw=1)
    ax.axhline(90, color=ps.INK_2, ls=":", lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("Gerçek test saatlerinde alarm oranı (%, log)")
    ax.set_ylabel("Olay yakalama oranı (%)")
    ax.set_title("Eşik seçiminin etkisi (eşikler doğrulama yüzdeliklerinden)")
    ax.legend(fontsize=8, loc="lower right")
    ps.save(fig, F / "15_threshold_tradeoff.png")

    # 16) Daire bazlı alarm oranı ve S1 yakalama
    a = apt.sort_values("alarm_rate")
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.5), sharey=True)
    yy = np.arange(len(a))
    axes[0].barh(yy + 0.2, a["alarm_rate_global_threshold"] * 100, color=ps.SERIES[1], height=0.38,
                 label="Yalnızca global eşik")
    axes[0].barh(yy - 0.2, a["alarm_rate"] * 100, color=ps.SERIES[0], height=0.38,
                 label="Daireye uyarlanmış eşik (nihai)")
    axes[0].set_yticks(yy, a.index)
    axes[0].legend(fontsize=8, loc="lower right")
    axes[0].axvline(10, color=ps.INK_2, ls=":", lw=1)
    axes[0].set_xlabel("Gerçek test saatlerinde alarm oranı (%)")
    axes[0].set_title("Daire bazlı model davranışı")
    axes[1].barh(yy, a["s1_detection"].fillna(0) * 100, color=ps.SERIES[2], height=0.7)
    axes[1].axvline(90, color=ps.INK_2, ls=":", lw=1)
    axes[1].set_xlabel("S1 gece sürekli akış yakalama (%)")
    for ax in axes:
        ax.grid(axis="y", visible=False)
    ps.save(fig, F / "16_per_apartment_behavior.png")

    # 17) Örnek olay: S1 enjeksiyonu (üst: tüketim, alt: skor – iki ayrı eksen paneli)
    s1 = [e for e in ev_test if e.scenario == "S1_night_continuous_flow"]
    ev = sorted(s1, key=lambda e: e.params["rate_l_per_hour"])[len(s1) // 4]
    s = pre.slots[pre.slots["apartment"] == ev.apartment].drop(columns="apartment").reset_index(drop=True)
    lo = (ev.start_utc - pd.Timedelta(days=config.HISTORY_DAYS + 1)).floor("h")
    hi = ev.end_utc.floor("h") + pd.Timedelta(hours=10, minutes=50)
    w = s[(s["slot_utc"] >= lo) & (s["slot_utc"] <= hi)][["slot_utc", "liters", "observed"]].reset_index(drop=True)
    inj = slots_to_hourly(inject(w, ev))
    cln = slots_to_hourly(w.drop(columns=[c for c in ("active", "run_slots") if c in w]))
    sc_inj = det.score_hourly(inj, ev.apartment)
    sc_cln = det.score_hourly(cln, ev.apartment)
    view = slice(-36, None)
    xi = sc_inj["hour_utc"].dt.tz_convert(config.LOCAL_TZ).dt.tz_localize(None).iloc[view]
    fig, axes = plt.subplots(2, 1, figsize=(10, 5.2), sharex=True, gridspec_kw={"height_ratios": [1, 1]})
    axes[0].bar(xi, sc_cln["consumption_liters"].iloc[view], width=0.035, color=ps.SERIES[0], label="Gerçek tüketim")
    axes[0].bar(xi, (sc_inj["consumption_liters"] - sc_cln["consumption_liters"]).iloc[view], width=0.035,
                bottom=sc_cln["consumption_liters"].iloc[view], color=ps.SERIES[1], label="Enjekte edilen akış")
    axes[0].set_ylabel("L / saat")
    axes[0].legend(fontsize=8)
    axes[0].set_title(f"Örnek S1 olayı – {ev.apartment}, {ev.params['rate_l_per_hour']:.1f} L/saat sürekli akış")
    axes[1].plot(xi, sc_cln["anomaly_score"].iloc[view], color=ps.SERIES[0], label="Enjeksiyonsuz skor")
    axes[1].plot(xi, sc_inj["anomaly_score"].iloc[view], color=ps.SERIES[1], label="Enjeksiyonlu skor")
    axes[1].axhline(th["suspicious"], color=ps.INK_2, ls="--", lw=1)
    axes[1].axhline(th["anomalous"], color=ps.INK, lw=1)
    axes[1].set_ylabel("Anomali skoru")
    axes[1].legend(fontsize=8, loc="upper left")
    import matplotlib.dates as mdates
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m %H:%M"))
    ps.save(fig, F / "17_example_night_flow_event.png")


def write_tables(R: dict) -> None:
    L = ["# Değerlendirme tabloları (otomatik üretildi)", ""]
    th = R["thresholds"]
    L += [f"Eşikler: Şüpheli ≥ {th['suspicious']:.4f} (doğrulama q={th['suspicious_quantile']}), "
          f"Anormal ≥ {th['anomalous']:.4f} (q={th['anomalous_quantile']})", ""]
    L += ["## Gerçek veride alarm oranları", "",
          "| Küme | Saat | Saat alarm (≥Şüpheli) | Saat Anormal | Gece saat alarm | Daire-gün alarm | Daire-gün Anormal |",
          "|---|---|---|---|---|---|---|"]
    for k, lab in [("real_train", "Eğitim"), ("real_validation", "Doğrulama"), ("real_test", "Test (tümü)"),
                   ("real_test_selected_normal", "Test (seçilmiş normal)")]:
        r = R[k]
        L.append(f"| {lab} | {r['n_hours']} | %{100 * r['hour_alarm_rate_suspicious_or_higher']:.2f} | "
                 f"%{100 * r['hour_alarm_rate_anomalous']:.2f} | %{100 * r['night_hour_alarm_rate']:.2f} | "
                 f"%{100 * r['apartment_day_alarm_rate']:.2f} | %{100 * r['apartment_day_anomalous_rate']:.2f} |")
    g = R["global_threshold_only"]
    L += ["", "## İlk sürüm (yalnızca global eşik) – şeffaflık için", "",
          "| Küme | Saat alarm | Daire-gün alarm | S1 | S2 | S3 | S4 |", "|---|---|---|---|---|---|---|"]
    for k, lab in [("validation", "Doğrulama"), ("test", "Test")]:
        r = g[f"real_{k}"]
        det_ = {x["scenario"]: x["detection_rate"] for x in g[f"synthetic_{k}"]}
        L.append(f"| {lab} | %{100 * r['hour_alarm_rate_suspicious_or_higher']:.2f} | "
                 f"%{100 * r['apartment_day_alarm_rate']:.2f} | " +
                 " | ".join(f"%{100 * det_[s_]:.1f}" for s_ in SCEN_TR) + " |")
    for key, lab in [("synthetic_validation", "Doğrulama"), ("synthetic_test", "Test")]:
        L += ["", f"## Sentetik olay yakalama – {lab}", "",
              "| Senaryo | Olay | Yakalama (≥Şüpheli) | Yakalama (Anormal) | Saat bazlı | Medyan max skor |",
              "|---|---|---|---|---|---|"]
        for r in R[key]:
            L.append(f"| {SCEN_TR[r['scenario']]} | {r['n_events']} | %{100 * r['detection_rate']:.1f} | "
                     f"%{100 * r['detection_rate_anomalous']:.1f} | %{100 * r['hour_level_detection']:.1f} | "
                     f"{r['median_max_score']:.3f} |")
    L += ["", "## Eşik taraması (test)", "",
          "| Doğrulama q | Eşik | Test alarm | S1 | S2 | S3 | S4 |", "|---|---|---|---|---|---|---|"]
    for r in R["threshold_sweep"]:
        L.append(f"| {r['valid_quantile']} | {r['threshold']:.4f} | %{100 * r['test_real_hour_alarm_rate']:.2f} | "
                 f"%{100 * r['test_detect_S1']:.1f} | %{100 * r['test_detect_S2']:.1f} | "
                 f"%{100 * r['test_detect_S3']:.1f} | %{100 * r['test_detect_S4']:.1f} |")
    c = R["model_scope_comparison"]
    L += ["", "## Global vs daire bazlı model", "",
          "| Model | Küme | S1 | S2 | S3 | S4 | Gerçek alarm | Daireler arası alarm std | En yüksek daire alarmı | >%10 daire |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for m in ["global", "global_adaptive_threshold", "per_apartment"]:
        for k in ["validation", "test"]:
            r = c[m][k]
            d = r["detection"]
            L.append(f"| {m} | {k} | " + " | ".join(f"%{100 * d.get(s, float('nan')):.1f}" for s in SCEN_TR) +
                     f" | %{100 * r['real_hour_alarm_rate']:.2f} | {100 * r['alarm_rate_std_across_apartments']:.2f} pp"
                     f" | %{100 * r['max_apartment_alarm_rate']:.1f} | {r['n_apartments_alarm_gt_10pct']} |")
    L += ["", "## Hiperparametre duyarlılığı (yalnızca doğrulama)", "",
          "| n_estimators | max_samples | S1 | S2 | S3 | S4 | Ortalama |", "|---|---|---|---|---|---|---|"]
    for r in R["hyperparameter_study_validation"]:
        L.append(f"| {r['n_estimators']} | {r['max_samples']} | %{100 * r['valid_detect_S1']:.1f} | "
                 f"%{100 * r['valid_detect_S2']:.1f} | %{100 * r['valid_detect_S3']:.1f} | "
                 f"%{100 * r['valid_detect_S4']:.1f} | %{100 * r['valid_detect_mean']:.1f} |")
    L += ["", "## S1 yakalama – debiye göre (test)", "", "| Debi (L/saat) | Yakalama |", "|---|---|"]
    for k, v in R["s1_detection_by_rate_test"].items():
        L.append(f"| {k} | %{100 * v:.1f} |")
    st = R["stress_low_rate_test"]
    L += ["", "## Stres testi – düşük debili gece sızıntısı (1–6 L/saat, test)", "",
          f"Toplam: {st['n_events']} olay, yakalama (≥Şüpheli) %{100 * st['detection_rate']:.1f}, "
          f"Anormal %{100 * st['detection_rate_anomalous']:.1f}", "", "| Debi (L/saat) | Yakalama |", "|---|---|"]
    for k, v in st["by_rate_l_per_hour"].items():
        L.append(f"| {k} | %{100 * v:.1f} |")
    L += ["", "## Enjeksiyonsuz pencerenin zaten alarm verme oranı (test)", ""]
    for k, v in R["synthetic_test_clean_window_flag_rate"].items():
        L.append(f"- {SCEN_TR[k]}: %{100 * v:.1f}")
    with open(config.REPORTS_DIR / "evaluation_tables.md", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    res = run_evaluation()
    print(open(config.REPORTS_DIR / "evaluation_tables.md", encoding="utf-8").read())
    print("süre:", res["runtime_seconds"], "sn")
