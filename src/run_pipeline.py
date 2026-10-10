"""Tüm AI hattını baştan sona çalıştırır.

    venv\\Scripts\\python.exe -m src.run_pipeline            # hepsi
    venv\\Scripts\\python.exe -m src.run_pipeline --skip-eda # EDA grafikleri hariç

Adımlar: ön işleme → EDA → profil + eğitim → değerlendirme (sentetik testler dahil).
Ham CSV değiştirilmez; tüm çıktılar data/processed, models, outputs altına yazılır.
"""
from __future__ import annotations

import argparse
import logging
import time

from . import config


def main() -> None:
    ap = argparse.ArgumentParser(description="WaterWise AI hattı")
    ap.add_argument("--skip-eda", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()

    from .data_preprocessing import run_preprocessing
    print("[1/4] Veri ön işleme…")
    pre = run_preprocessing()
    c = pre.report["cleaning"]
    print(f"      {c['rows_after_cleaning']} kayıt, kapsama %{100 * c['apartment_hour_coverage']:.1f}")

    if not args.skip_eda:
        from .eda import run_eda
        print("[2/4] Keşifsel veri analizi…")
        run_eda(pre)

    from .train_model import run_training
    print("[3/4] Normal profil + Isolation Forest eğitimi…")
    tr = run_training(pre)
    print(f"      eşikler: {tr['thresholds']['suspicious']:.4f} / {tr['thresholds']['anomalous']:.4f}")

    if not args.skip_eval:
        from .evaluate_model import run_evaluation
        print("[4/4] Değerlendirme + sentetik anomali testleri…")
        run_evaluation()
        print("      →", config.REPORTS_DIR / "evaluation_tables.md")
    print(f"Tamamlandı ({time.time() - t0:.0f} sn).")


if __name__ == "__main__":
    main()
