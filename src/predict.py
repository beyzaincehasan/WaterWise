"""WaterWise anomali tahmin modülü (backend entegrasyonu için).

Hızlı kullanım
--------------
    from src.predict import predict_anomaly

    result = predict_anomaly(
        apartment_id="APT_005",
        records=[{"timestamp": "2022-10-05T02:10:00+02:00", "consumption_liters": 3.0}, ...],
        target_timestamp="2022-10-05T02:00:00+02:00",   # değerlendirilecek saat
        history_start="2022-09-07T00:00:00+02:00",      # kayıtların kapsadığı izleme başlangıcı
    )

Girdi sözleşmesi (ayrıntı: docs/backend_integration.md)
-------------------------------------------------------
* `records`: dairenin HAM 10 dakikalık sensör kayıtları (tüm armatürler,
  sıcak+soğuk). Her kayıt: `timestamp` + `consumption_liters` (veya ham CSV
  biçiminde m³ olarak `value`). Saat dilimi olmayan zaman damgaları
  Europe/Stockholm yerel saati kabul edilir (veri setiyle aynı).
* Sensörler yalnızca tüketim olduğunda kayıt üretir. Bu yüzden
  [history_start, hedef saatin sonu] aralığında kaydı olmayan 10 dakikalık
  dilimler 0 L kabul edilir. İzleme kesintileri `unobserved_intervals` ile
  bildirilmelidir; aksi halde sıfır tüketim sayılır.
* Model geçmiş bağlam ister: hedef saatten önceki en az 7 gün, ideal olarak
  28 gün. Daha az geçmişte eğitim dönemi normal profili yedek olarak kullanılır
  ve sonuçta uyarı (`warnings`) verilir. Tek bir kayıttan tahmin YAPILMAZ.
* Hedef saatten sonraki kayıtlar yok sayılır (gelecek bilgisi kullanılmaz).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd

from . import config
from .feature_engineering import (FEATURE_COLUMNS, compute_features, records_to_slots,
                                  slots_to_hourly, to_utc)
from .normal_profile import get_profile

DISCLAIMER = ("Bu sonuç tüketim davranışına dayalı bir olası kaçak / olağandışı kullanım uyarısıdır; "
              "kesin tesisat kaçağı teşhisi değildir.")


class WaterWiseInputError(ValueError):
    """Geçersiz veya yetersiz girdi. `code` alanı makine tarafından okunabilir hata kodudur."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class WaterWiseModelError(RuntimeError):
    """Model dosyaları bulunamadı / uyumsuz."""


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _f(x, nd=3):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(v) else round(v, nd)


def _iso_utc(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value, name: str) -> pd.Timestamp:
    try:
        ts = to_utc([value]).iloc[0]
    except Exception as exc:  # noqa: BLE001
        raise WaterWiseInputError("INVALID_TIMESTAMP", f"{name} çözümlenemedi: {value!r}") from exc
    if pd.isna(ts):
        raise WaterWiseInputError("INVALID_TIMESTAMP", f"{name} boş olamaz")
    return ts


def normalize_records(records: Any, apartment_id: str | None = None) -> pd.DataFrame:
    """Kayıtları doğrular ve [timestamp_utc, value_liters] tablosuna çevirir."""
    if records is None:
        raise WaterWiseInputError("NO_RECORDS", "records boş olamaz")
    if isinstance(records, pd.DataFrame):
        df = records.copy()
    else:
        try:
            df = pd.DataFrame(list(records))
        except Exception as exc:  # noqa: BLE001
            raise WaterWiseInputError("INVALID_RECORDS", "records bir sözlük listesi veya DataFrame olmalı") from exc
    if df.empty:
        raise WaterWiseInputError("NO_RECORDS", "En az bir tüketim kaydı gereklidir")
    if "timestamp" not in df.columns:
        raise WaterWiseInputError("MISSING_FIELD", "Her kayıtta 'timestamp' alanı olmalı")
    if "consumption_liters" in df.columns:
        liters = pd.to_numeric(df["consumption_liters"], errors="coerce")
    elif "value_liters" in df.columns:
        liters = pd.to_numeric(df["value_liters"], errors="coerce")
    elif "value" in df.columns:          # ham CSV biçimi: m³
        liters = pd.to_numeric(df["value"], errors="coerce") * config.M3_TO_LITERS
    else:
        raise WaterWiseInputError("MISSING_FIELD", "Her kayıtta 'consumption_liters' (veya m³ olarak 'value') olmalı")
    if liters.isna().any() or not np.isfinite(liters.to_numpy()).all():
        raise WaterWiseInputError("INVALID_VALUE", "Tüketim değerleri sayısal ve sonlu olmalı")
    if (liters < 0).any():
        raise WaterWiseInputError("NEGATIVE_VALUE", "Tüketim değerleri negatif olamaz")
    if apartment_id is not None and "apartment" in df.columns:
        other = df["apartment"].dropna().astype(str)
        if (other != apartment_id).any():
            raise WaterWiseInputError("APARTMENT_MISMATCH",
                                      "records içinde farklı bir daireye ait kayıt var")
    try:
        ts = to_utc(df["timestamp"])
    except Exception as exc:  # noqa: BLE001
        raise WaterWiseInputError("INVALID_TIMESTAMP", "Zaman damgaları çözümlenemedi") from exc
    if ts.isna().any():
        raise WaterWiseInputError("INVALID_TIMESTAMP", "Boş zaman damgası var")
    return pd.DataFrame({"timestamp_utc": ts.reset_index(drop=True),
                         "value_liters": liters.astype(float).reset_index(drop=True)})


# ---------------------------------------------------------------------------
# Dedektör
# ---------------------------------------------------------------------------
class WaterWiseAnomalyDetector:
    """Eğitilmiş Isolation Forest + normal profiller; yeniden eğitim gerektirmez."""

    def __init__(self, model_path: Path | str = config.MODEL_FILE,
                 profiles_path: Path | str = config.PROFILES_FILE,
                 metadata_path: Path | str = config.METADATA_FILE):
        for p in (model_path, profiles_path):
            if not Path(p).exists():
                raise WaterWiseModelError(f"Model dosyası bulunamadı: {p}. Önce `python -m src.train_model` çalıştırın.")
        bundle = joblib.load(model_path)
        if bundle.get("feature_columns") != FEATURE_COLUMNS:
            raise WaterWiseModelError("Model özellik listesi kod ile uyumsuz; modeli yeniden eğitin.")
        self.model = bundle["model"]
        self.thresholds = bundle["thresholds"]
        self.apartment_thresholds = bundle.get("apartment_thresholds", {})
        self.model_version = bundle.get("model_version", "unknown")
        with open(profiles_path, encoding="utf-8") as f:
            self.profiles = json.load(f)
        self.metadata = {}
        if Path(metadata_path).exists():
            with open(metadata_path, encoding="utf-8") as f:
                self.metadata = json.load(f)

    # ---- skor ve durum --------------------------------------------------
    def score(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        return -self.model.score_samples(np.asarray(X, dtype=float))

    def thresholds_for(self, apartment_id: str | None) -> tuple[dict, str]:
        """(eşikler, kapsam) – daireye özel (yalnızca yukarı yönlü) eşik varsa o, yoksa global."""
        t = self.apartment_thresholds.get(apartment_id) if apartment_id else None
        if t is not None:
            return t, "apartment"
        return self.thresholds, "global"

    def classify(self, scores: np.ndarray, apartment_id: str | None = None) -> np.ndarray:
        t, _ = self.thresholds_for(apartment_id)
        s = np.asarray(scores)
        return np.where(s >= t["anomalous"], config.STATUS_ANOMALOUS,
                        np.where(s >= t["suspicious"], config.STATUS_SUSPICIOUS, config.STATUS_NORMAL))

    def known_apartments(self) -> list[str]:
        return sorted(self.profiles["apartments"])

    def score_hourly(self, hourly: pd.DataFrame, apartment_id: str) -> pd.DataFrame:
        """Saatlik seriden (slots_to_hourly çıktısı) özellik + skor + durum üretir.

        Özelliği hesaplanamayan (gözlenmeyen) saatlerde skor/durum NaN kalır.
        """
        profile, _ = get_profile(self.profiles, apartment_id)
        f = compute_features(hourly, profile)
        f["anomaly_score"] = np.nan
        f["status"] = None
        ok = f["feature_complete"].to_numpy()
        if ok.any():
            s = self.score(f.loc[ok, FEATURE_COLUMNS])
            f.loc[ok, "anomaly_score"] = s
            f.loc[ok, "status"] = self.classify(s, apartment_id)
        return f

    def build_hourly(self, apartment_id: str, records: Any, start_utc: pd.Timestamp, end_utc: pd.Timestamp,
                     unobserved_intervals: Iterable | None = None) -> pd.DataFrame:
        if isinstance(records, pd.DataFrame) and {"timestamp_utc", "value_liters"} <= set(records.columns):
            recs = records            # normalize_records çıktısı
        else:
            recs = normalize_records(records, apartment_id)
        recs = recs[(recs["timestamp_utc"] >= start_utc) & (recs["timestamp_utc"] <= end_utc)]
        iv = None
        if unobserved_intervals:
            iv = [(_parse_ts(a, "unobserved_intervals"), _parse_ts(b, "unobserved_intervals"))
                  for a, b in unobserved_intervals]
        slots = records_to_slots(recs, start_utc, end_utc, iv)
        return slots_to_hourly(slots)

    # ---- açıklama --------------------------------------------------------
    def explain(self, row: Mapping, profile: Mapping, apartment_specific: bool) -> list[dict]:
        h = int(row["hour_local"])
        c = float(row["consumption_liters"])
        mean_h = float(np.nan_to_num(profile["hourly_mean_liters"][h]))
        p95_list = profile.get("hourly_p95_liters") or [None] * 24
        p95_h = float(np.nan_to_num(p95_list[h] if p95_list[h] is not None else mean_h * 3))
        prob_list = profile.get("hourly_active_probability") or [None] * 24
        prob_h = prob_list[h]
        cont = float(row["continuous_activity_min"])
        active = int(row["active_slots"])
        night = bool(row["is_night"])
        reasons = []
        if night and (active >= 4 or cont >= 60) and c > 0:
            reasons.append({"code": "NIGHT_CONTINUOUS_FLOW",
                            "text": f"Gece saatlerinde {cont:.0f} dakika boyunca kesintisiz tüketim kaydı "
                                    f"({active}/6 aktif 10 dk dilim). Olası sürekli akış."})
        if c > max(2 * p95_h, 5.0):
            reasons.append({"code": "HIGH_CONSUMPTION",
                            "text": f"Bu saat için olağandışı yüksek tüketim: {c:.0f} L "
                                    f"(normal ortalama {mean_h:.1f} L, normal üst sınır {p95_h:.0f} L)."})
        if prob_h is not None and prob_h < 0.15 and c >= max(10.0, 2 * p95_h):
            reasons.append({"code": "UNUSUAL_HOUR",
                            "text": f"Dairenin bu saatte tüketim yapma olasılığı düşük (%{100 * prob_h:.0f}), "
                                    f"ancak {c:.0f} L tüketim kaydedildi."})
        if active <= 2 and c >= max(30.0, 3 * p95_h):
            reasons.append({"code": "SHORT_SPIKE",
                            "text": f"Kısa sürede ({active * 10} dk) {c:.0f} L ani tüketim artışı."})
        cont_p99 = (profile.get("continuity") or {}).get("p99_minutes")
        if cont_p99 and cont > max(cont_p99, 60) and not any(r["code"] == "NIGHT_CONTINUOUS_FLOW" for r in reasons):
            reasons.append({"code": "LONG_CONTINUOUS_USE",
                            "text": f"{cont:.0f} dakikalık kesintisiz kullanım, dairenin olağan "
                                    f"üst sınırının ({cont_p99:.0f} dk) üzerinde."})
        dev = float(row["deviation_from_normal"])
        if not reasons and dev > 1.0:
            ratio = (c + 1) / (float(row["historical_same_hour_mean"]) + 1)
            reasons.append({"code": "DEVIATION_FROM_NORMAL",
                            "text": f"Tüketim, son {config.HISTORY_DAYS} günde aynı saatteki ortalamanın "
                                    f"yaklaşık {ratio:.1f} katı."})
        if not reasons:
            reasons.append({"code": "PATTERN_COMBINATION",
                            "text": "Tüketim miktarı, zamanı ve sürekliliğinin birleşimi dairenin geçmiş "
                                    "örüntüsünden farklı."})
        if not apartment_specific:
            reasons.append({"code": "GENERIC_PROFILE", "text": "Daireye özel profil yok; bina geneli profil kullanıldı."})
        return reasons

    @staticmethod
    def compose_message(status: str, reasons: list[dict]) -> str:
        if status == config.STATUS_NORMAL:
            return "Su tüketimi dairenin normal tüketim aralığında."
        codes = {r["code"] for r in reasons}
        if "NIGHT_CONTINUOUS_FLOW" in codes:
            head = "Gece saatlerinde olağandışı su tüketimi tespit edildi."
            action = "Olası sürekli akış (açık musluk, rezervuar arızası veya kaçak) kontrol edilmelidir."
        elif "HIGH_CONSUMPTION" in codes:
            head = "Normal tüketim profilinin belirgin biçimde üzerinde tüketim tespit edildi."
            action = "Açık kalan musluk veya olağandışı kullanım olup olmadığı kontrol edilmelidir."
        elif "UNUSUAL_HOUR" in codes:
            head = "Dairenin alışılmadık bir saatinde yoğun su tüketimi tespit edildi."
            action = "Bu kullanımın bilinçli olup olmadığı kontrol edilmelidir."
        elif "SHORT_SPIKE" in codes:
            head = "Kısa süreli ani su tüketimi artışı tespit edildi."
            action = "Tekrar ederse tesisat kontrol edilmelidir."
        elif "LONG_CONTINUOUS_USE" in codes:
            head = "Olağandışı uzun süreli kesintisiz su kullanımı tespit edildi."
            action = "Olası sürekli akış kontrol edilmelidir."
        else:
            head = "Dairenin geçmiş tüketim örüntüsünden sapma tespit edildi."
            action = "Tüketimin takip edilmesi önerilir."
        if status == config.STATUS_SUSPICIOUS:
            return f"{head} Durum şüpheli; {action[0].lower() + action[1:]}"
        return f"{head} {action}"

    def _result_row(self, apartment_id: str, row: Mapping, profile: Mapping, apt_specific: bool,
                    warnings: list[str]) -> dict:
        h = int(row["hour_local"])
        ts = pd.Timestamp(row["hour_utc"])
        status = row["status"]
        th, th_scope = self.thresholds_for(apartment_id)
        reasons = self.explain(row, profile, apt_specific) if status != config.STATUS_NORMAL else []
        p95 = (profile.get("hourly_p95_liters") or [None] * 24)[h]
        c = float(row["consumption_liters"])
        return {
            "apartment_id": apartment_id,
            "timestamp": _iso_utc(ts),
            "timestamp_local": ts.tz_convert(config.LOCAL_TZ).isoformat(),
            "period_minutes": 60,
            "consumption_liters": _f(c, 1),
            "status": status,
            "anomaly_score": _f(row["anomaly_score"], 4),
            "thresholds": {"suspicious": _f(th["suspicious"], 4),
                           "anomalous": _f(th["anomalous"], 4),
                           "scope": th_scope},
            "normal_consumption_liters": _f(profile["hourly_mean_liters"][h], 1),
            "normal_upper_liters": _f(p95, 1),
            "historical_same_hour_mean_liters": _f(row["historical_same_hour_mean"], 1),
            "rolling_24h_mean_liters": _f(row["rolling_24h_mean"], 2),
            "rolling_7d_mean_liters": _f(row["rolling_7d_mean"], 2),
            "active_10min_intervals": int(row["active_slots"]),
            "continuous_activity_minutes": int(row["continuous_activity_min"]),
            "is_night": bool(row["is_night"]),
            "reasons": reasons,
            "message": self.compose_message(status, reasons),
            "history": {
                "sufficient": bool(row["history_sufficient"]),
                "profile_fallback_used": bool(row["fallback_used"]),
                "apartment_profile_available": apt_specific,
            },
            "warnings": list(warnings),
            "disclaimer": DISCLAIMER,
            "model_version": self.model_version,
        }

    # ---- genel API --------------------------------------------------------
    def evaluate(self, apartment_id: str, records: Any, start: Any = None, end: Any = None,
                 history_start: Any = None, unobserved_intervals: Iterable | None = None) -> list[dict]:
        """[start, end] aralığındaki her saat için sonuç listesi döndürür.

        Geçmiş bağlam `history_start`'tan itibaren kayıtlardan hesaplanır.
        """
        if not apartment_id or not isinstance(apartment_id, str):
            raise WaterWiseInputError("INVALID_APARTMENT", "apartment_id boş olmayan bir metin olmalı")
        recs = normalize_records(records, apartment_id)
        last_hour = recs["timestamp_utc"].max().floor("h")
        end_h = _parse_ts(end, "end").floor("h") if end is not None else last_hour
        start_h = _parse_ts(start, "start").floor("h") if start is not None else end_h
        if start_h > end_h:
            raise WaterWiseInputError("INVALID_RANGE", "start, end'den sonra olamaz")
        hist = (_parse_ts(history_start, "history_start").floor("h") if history_start is not None
                else recs["timestamp_utc"].min().floor("h"))
        if hist > start_h:
            raise WaterWiseInputError("INVALID_RANGE", "history_start hedef saatten sonra olamaz")
        window_end = end_h + pd.Timedelta(minutes=60 - config.SLOT_MINUTES)
        hourly = self.build_hourly(apartment_id, recs, hist, window_end, unobserved_intervals)
        scored = self.score_hourly(hourly, apartment_id)
        profile, apt_specific = get_profile(self.profiles, apartment_id)

        history_hours = int((start_h - hist) / pd.Timedelta(hours=1))
        base_warn = []
        if not apt_specific:
            base_warn.append("UNKNOWN_APARTMENT: daireye özel normal profil yok, bina geneli profil kullanıldı")
        if history_hours < 24 * 7:
            base_warn.append(f"SHORT_HISTORY: hedef saatten önce yalnızca {history_hours} saat geçmiş var; "
                             f"en az 7 gün (ideal {config.HISTORY_DAYS} gün) önerilir")
        out = []
        sel = scored[(scored["hour_utc"] >= start_h) & (scored["hour_utc"] <= end_h)]
        for _, row in sel.iterrows():
            if pd.isna(row["anomaly_score"]):
                raise WaterWiseInputError(
                    "TARGET_NOT_OBSERVED",
                    f"{_iso_utc(row['hour_utc'])} saati gözlenmeyen bir aralıkta; değerlendirilemez")
            w = list(base_warn)
            if row["fallback_used"]:
                w.append("PROFILE_FALLBACK: geçmiş bağlam yetersiz, bazı taban değerler eğitim profilinden alındı")
            out.append(self._result_row(apartment_id, row, profile, apt_specific, w))
        return out

    def predict(self, apartment_id: str, records: Any, target_timestamp: Any = None,
                history_start: Any = None, unobserved_intervals: Iterable | None = None) -> dict:
        """Tek bir saat (target_timestamp'in içinde bulunduğu saat) için sonuç."""
        res = self.evaluate(apartment_id, records, start=target_timestamp, end=target_timestamp,
                            history_start=history_start, unobserved_intervals=unobserved_intervals)
        return res[-1]


@lru_cache(maxsize=4)
def _cached_detector(model_path: str, profiles_path: str, metadata_path: str) -> WaterWiseAnomalyDetector:
    return WaterWiseAnomalyDetector(model_path, profiles_path, metadata_path)


def load_detector(model_dir: Path | str | None = None) -> WaterWiseAnomalyDetector:
    """Model dosyalarını bir kez yükler ve önbelleğe alır (uygulama açılışında çağırın)."""
    d = Path(model_dir) if model_dir else config.MODELS_DIR
    return _cached_detector(str(d / config.MODEL_FILE.name), str(d / config.PROFILES_FILE.name),
                            str(d / config.METADATA_FILE.name))


def predict_anomaly(apartment_id: str, records: Sequence[Mapping] | pd.DataFrame,
                    target_timestamp: Any = None, history_start: Any = None,
                    unobserved_intervals: Iterable | None = None,
                    detector: WaterWiseAnomalyDetector | None = None) -> dict:
    """Bir dairenin belirli bir saati için anomali sonucu (JSON-uyumlu sözlük).

    Parameters
    ----------
    apartment_id : "APT_001" … "APT_028" (bilinmeyen dairelerde bina geneli profil + uyarı)
    records : ham 10 dk kayıtları; her biri {"timestamp", "consumption_liters"}.
        Hedef saati ve tercihen önceki 28 günü kapsamalıdır.
    target_timestamp : değerlendirilecek saat (o saatin içindeki herhangi bir an).
        Verilmezse en son kaydın saati kullanılır.
    history_start : kayıtların kapsadığı izleme döneminin başlangıcı. Verilmezse
        en eski kaydın saati kabul edilir.
    unobserved_intervals : [(başlangıç, bitiş), ...] izleme kesintileri.
    """
    det = detector or load_detector()
    return det.predict(apartment_id, records, target_timestamp, history_start, unobserved_intervals)
