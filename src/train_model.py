"""Isolation Forest eğitimi ve eşik kalibrasyonu.

Analiz birimi: daire-saat (UTC saat; özelliklerde yerel saat kullanılır).
Model: TÜM daireler için tek (global) model; özellikler dairenin kendi
geçmişine göre normalize edilmiş sapmalar içerdiğinden daireler arası ölçek
farkı büyük ölçüde giderilir (gerekçe: docs/ai_methodology.md, bölüm 8).

Zamansal ayrım (config):
  eğitim     2020-01-01 – 2021-11-22  → model + normal profil
  doğrulama  2022-02-17 – 2022-06-30  → eşik kalibrasyonu, tasarım kararları
  test       2022-07-01 – 2023-01-31  → yalnızca nihai raporlama (bir kez)

Skor tanımı: anomaly_score = -IsolationForest.score_samples(X)
  Liu vd. (2008) anomali skoru s(x) = 2^(-E[h(x)]/c(n)), aralık (0, 1].
  Yüksek değer = daha olağandışı. ~0.5 ve altı tipik; 1'e yaklaştıkça
  kolay izole edilen (anormal) gözlem. Bu bir OLASILIK DEĞİLDİR.
"""
from __future__ import annotations

import json
import logging
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest

from . import config
from .feature_engineering import FEATURE_COLUMNS, compute_features
from .normal_profile import build_profiles, get_profile, save_profiles

log = logging.getLogger(__name__)


def build_feature_table(hourly: pd.DataFrame, profiles: dict) -> pd.DataFrame:
    """Her dairenin tüm saatlik serisi için nedensel özellikler."""
    frames = []
    for apt, grp in hourly.groupby("apartment"):
        prof, _ = get_profile(profiles, apt)
        f = compute_features(grp.drop(columns="apartment"), prof)
        f.insert(0, "apartment", apt)
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def period_mask(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, col: str = "hour_utc") -> pd.Series:
    return (df[col] >= start.tz_convert("UTC")) & (df[col] < end.tz_convert("UTC"))


def split_periods(features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    usable = features["observed"] & features["feature_complete"]
    train = features[period_mask(features, config.TRAIN_START, config.TRAIN_END) & usable
                     & features["history_sufficient"]]
    valid = features[period_mask(features, config.VALID_START, config.VALID_END) & usable]
    test = features[period_mask(features, config.TEST_START, config.TEST_END) & usable]
    return {"train": train, "valid": valid, "test": test}


def anomaly_scores(model: IsolationForest, X: pd.DataFrame | np.ndarray) -> np.ndarray:
    """(0, 1] aralığında Liu vd. anomali skoru; yüksek = daha olağandışı."""
    return -model.score_samples(np.asarray(X, dtype=float))


def fit_isolation_forest(X: pd.DataFrame, params: dict | None = None) -> IsolationForest:
    p = dict(config.IFOREST_PARAMS)
    if params:
        p.update(params)
    if isinstance(p.get("max_samples"), int):
        p["max_samples"] = min(p["max_samples"], len(X))
    model = IsolationForest(**p)
    model.fit(np.asarray(X, dtype=float))
    return model


def calibrate_thresholds(valid_scores: np.ndarray,
                         q_susp: float = config.SUSPICIOUS_QUANTILE,
                         q_anom: float = config.ANOMALOUS_QUANTILE) -> dict:
    return {
        "suspicious": float(np.quantile(valid_scores, q_susp)),
        "anomalous": float(np.quantile(valid_scores, q_anom)),
        "suspicious_quantile": q_susp,
        "anomalous_quantile": q_anom,
        "calibration_set": "doğrulama dönemi gerçek (etiketsiz) daire-saatleri",
    }


def calibrate_apartment_thresholds(valid: pd.DataFrame, valid_scores: np.ndarray, global_th: dict,
                                   min_hours: int = config.MIN_APARTMENT_CALIBRATION_HOURS) -> dict:
    """Daireye uyarlanmış eşikler – YALNIZCA YUKARI yönlü.

    eşik_daire = max(global eşik, dairenin doğrulama skorlarının aynı yüzdeliği)

    Yüksek hacimli (çok sensörlü, kalabalık) dairelerde global eşik çok sık
    alarm üretir; bu dairelerde eşik yükseltilir. Sessiz dairelerde global eşik
    korunur, böylece hassasiyet düşmez. Yetersiz doğrulama verisi olan veya
    bilinmeyen dairelerde global eşik kullanılır.
    """
    out = {}
    s = pd.Series(valid_scores, index=valid.index)
    for apt, grp in s.groupby(valid["apartment"]):
        if len(grp) < min_hours:
            continue
        qs = float(np.quantile(grp, global_th["suspicious_quantile"]))
        qa = float(np.quantile(grp, global_th["anomalous_quantile"]))
        out[apt] = {
            "suspicious": max(global_th["suspicious"], qs),
            "anomalous": max(global_th["anomalous"], qa),
            "n_valid_hours": int(len(grp)),
            "raised": bool(qs > global_th["suspicious"] or qa > global_th["anomalous"]),
        }
    return out


def classify(scores: np.ndarray, thresholds: dict) -> np.ndarray:
    s = np.asarray(scores)
    return np.where(s >= thresholds["anomalous"], config.STATUS_ANOMALOUS,
                    np.where(s >= thresholds["suspicious"], config.STATUS_SUSPICIOUS, config.STATUS_NORMAL))


def save_artifacts(model: IsolationForest, thresholds: dict, metadata: dict,
                   apartment_thresholds: dict | None = None) -> None:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "thresholds": thresholds,
        "apartment_thresholds": apartment_thresholds or {},
        "model_version": config.MODEL_VERSION,
        "sklearn_version": sklearn.__version__,
    }
    joblib.dump(bundle, config.MODEL_FILE, compress=3)
    with open(config.METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)


def run_training(pre=None, save: bool = True) -> dict:
    from .data_preprocessing import load_processed
    pre = pre or load_processed()
    t0 = time.time()
    profiles = build_profiles(pre.hourly, pre.slots)
    feats = build_feature_table(pre.hourly, profiles)
    parts = split_periods(feats)
    Xtr = parts["train"][FEATURE_COLUMNS]
    model = fit_isolation_forest(Xtr)
    val_scores = anomaly_scores(model, parts["valid"][FEATURE_COLUMNS])
    thresholds = calibrate_thresholds(val_scores)
    apt_thresholds = calibrate_apartment_thresholds(parts["valid"], val_scores, thresholds)
    tr_scores = anomaly_scores(model, Xtr)

    metadata = {
        "model_name": "WaterWise Isolation Forest anomali modeli",
        "model_version": config.MODEL_VERSION,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "algorithm": "sklearn.ensemble.IsolationForest",
        "model_scope": "global (tüm daireler için tek model, daireye göre normalize özellikler)",
        "analysis_unit": "daire-saat (UTC saat başı; yerel saat Europe/Stockholm özelliklerde)",
        "hyperparameters": {k: v for k, v in model.get_params().items()},
        "feature_columns": FEATURE_COLUMNS,
        "score_definition": ("anomaly_score = -score_samples(X), Liu vd. (2008) s(x)=2^(-E[h(x)]/c(n)), "
                             "aralık (0,1], yüksek = daha olağandışı; olasılık değildir"),
        "thresholds": thresholds,
        "apartment_thresholds": apt_thresholds,
        "status_rule": ("Daireye özel eşik varsa o, yoksa global eşik kullanılır. score >= anomalous → Anormal; "
                        "score >= suspicious → Şüpheli; aksi halde Normal"),
        "apartment_threshold_rule": ("eşik_daire = max(global eşik, dairenin doğrulama skor yüzdeliği); "
                                     f"en az {config.MIN_APARTMENT_CALIBRATION_HOURS} doğrulama saati gerekir"),
        "periods_local": {
            "train": [str(config.TRAIN_START), str(config.TRAIN_END)],
            "validation": [str(config.VALID_START), str(config.VALID_END)],
            "test": [str(config.TEST_START), str(config.TEST_END)],
        },
        "n_rows": {k: int(len(v)) for k, v in parts.items()},
        "n_apartments_train": int(parts["train"]["apartment"].nunique()),
        "train_score_quantiles": {str(q): float(np.quantile(tr_scores, q)) for q in [0.5, 0.9, 0.97, 0.99, 0.995]},
        "valid_score_quantiles": {str(q): float(np.quantile(val_scores, q)) for q in [0.5, 0.9, 0.97, 0.99, 0.995]},
        "history_requirements": {
            "history_days": config.HISTORY_DAYS,
            "min_same_hour_obs": config.MIN_SAME_HOUR_OBS,
            "min_24h_obs": config.MIN_24H_OBS,
            "min_7d_obs": config.MIN_7D_OBS,
        },
        "night_hours_local": [config.NIGHT_START_HOUR, config.NIGHT_END_HOUR],
        "timezone": config.LOCAL_TZ,
        "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                        "pandas": pd.__version__, "numpy": np.__version__},
        "training_seconds": round(time.time() - t0, 1),
        "files": {
            "model": config.MODEL_FILE.name,
            "profiles": config.PROFILES_FILE.name,
            "metadata": config.METADATA_FILE.name,
        },
    }
    if save:
        save_profiles(profiles)
        save_artifacts(model, thresholds, metadata, apt_thresholds)
        config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        feats.to_parquet(config.PROCESSED_DIR / "apartment_hourly_features.parquet", index=False)
    return {"model": model, "thresholds": thresholds, "apartment_thresholds": apt_thresholds, "profiles": profiles, "features": feats,
            "parts": parts, "metadata": metadata}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    out = run_training()
    m = out["metadata"]
    print(json.dumps({k: m[k] for k in ["n_rows", "thresholds", "train_score_quantiles",
                                        "valid_score_quantiles", "training_seconds"]}, indent=1, ensure_ascii=False))
