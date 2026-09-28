
# -*- coding: utf-8 -*-
"""CLI entrypoint — Release 4."""
from __future__ import annotations

import datetime
import logging
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import PathConfigError, load_settings, require_dir
from src import __version__
from src.cli import choose_source_file
from src.models import Config
from src.pipeline import run_analysis

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    print("=" * 60)
    print(f"  АНАЛИЗАТОР ИНВЕНТАРИЗАЦИЙ СЕТИ  v{__version__} (Release 4)")
    print("=" * 60)

    settings = load_settings()
    search_dir = settings.search_dir
    print(f"\nРабочая папка (исходные Excel):\n{search_dir}")
    print(f"Папка итоговых отчётов:\n{settings.output_dir}")

    try:
        require_dir(search_dir, "Папка исходных Excel-файлов")
    except PathConfigError as exc:
        print(f"\n{exc}")
        try:
            input("\nEnter для выхода...")
        except EOFError:
            pass
        return

    print("\n[1/2] Выберите файл ИНВЕНТАРИЗАЦИИ:")
    src = choose_source_file(str(search_dir))
    if not src or not os.path.exists(src):
        print("Файл инвентаризации не выбран.")
        try:
            input("\nEnter для выхода...")
        except EOFError:
            pass
        return

    print("\n[2/2] Выберите файл ОПРИХОДОВАНИЯ ИЗЛИШКОВ (закрытие смены):")
    print("      Нужны колонки: «Закрытие смены количество», «Закрытие смены сумма».")
    cap = choose_source_file(str(search_dir))
    if not cap or not os.path.exists(cap):
        print("Файл оприходования не выбран — отчёт без сверки оприходования.")
        cap = None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = settings.output_dir if settings.output_dir.is_dir() else Path(os.path.dirname(src))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(out_dir / f"Анализ_сеть_{Path(src).stem}_{ts}.xlsx")
    catalog = os.path.join(os.path.dirname(src), settings.catalog_filename)

    cfg = Config(
        input_path=src,
        output_path=out,
        period_days=settings.period_days,
        catalog_path=catalog if os.path.exists(catalog) else None,
        enable_cross_store=settings.enable_cross_store,
        capitalization_path=cap,
    )

    try:
        result = run_analysis(cfg)
        print(f"\nИтоговый файл:\n{result}")
    except FileNotFoundError as exc:
        log.error("ОШИБКА: не найден обязательный файл.\n%s", exc)
    except PathConfigError as exc:
        log.error("ОШИБКА:\n%s", exc)
    except Exception as exc:
        log.error("ОШИБКА: %s", exc)
        traceback.print_exc()

    try:
        input("\nEnter для выхода...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
