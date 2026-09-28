# -*- coding: utf-8 -*-
"""Загрузка выгрузки. Локальный эталон используется, если файл есть.

Если эталона нет, строки не выдумываются: категория остаётся пустой меткой,
анализ продолжается по справочникам config.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from src.catalog import enrich_dataframe, load_catalog
from src.master_hierarchy import get_master_hierarchy
from src.parser import filter_by_period, parse_network_excel
from src.text_normalize import infer_unit, sku_key


def load_inventory(
    path: str | Path,
    period_days: int = 30,
    end_date: Optional[datetime.date] = None,
    catalog_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, object, list]:
    notes = []
    df, meta = parse_network_excel(str(path))
    end = end_date or meta.date_max
    df = filter_by_period(df, period_days, end)
    if df.empty:
        raise ValueError("После фильтра периода строк не осталось. Расширьте период или проверьте даты документов.")
    try:
        master = get_master_hierarchy()
        catalog = load_catalog(catalog_path)
        df = enrich_dataframe(df, catalog, hierarchy=master)
        notes.append(f"Эталон иерархии загружен: {master.source_file}, SKU {len(master.items)}.")
    except FileNotFoundError:
        df = _without_hierarchy(df)
        notes.append(
            "Эталон иерархии недоступен. Категории не выдуманы. "
            "Классификация идёт по config/item_scope_classification.csv и config/scope_rules.csv."
        )
    return df, meta, notes


def _without_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sku_key"] = out["наименование"].apply(sku_key)
    out["единица"] = out["наименование"].apply(infer_unit)
    out["артикул"] = out["sku_key"].str[:20]
    out["category_group"] = out["sku_key"].map(lambda key: f"__unmatched__:{key}" if key else "Не найдено в справочнике")
    out["category_label"] = "Не найдено в справочнике"
    out["category_method"] = "missing_hierarchy"
    out["category_fallback"] = True
    out["hierarchy_matched"] = False
    out["hierarchy_path"] = ""
    out["leaf_group"] = ""
    out["level_0"] = ""
    out["level_1"] = ""
    return out
