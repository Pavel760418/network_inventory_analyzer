# -*- coding: utf-8 -*-
"""Классификация контура: СП, хозтовары, тара, упаковка, без класса.

Точечный справочник важнее правил. Если совпадения нет, строка остаётся
«unclassified» и не исключается из операционного контура.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import ITEM_SCOPE, NON_CORE_SCOPES, SCOPE_RULES

FLAG_COLS = [
    "include_in_production_score",
    "include_in_store_rating",
    "include_in_shortage_top",
    "include_in_regrading",
]


def _flag(value: Any, default: bool = True) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip().lower()
    if text in ("", "nan"):
        return default
    return text in ("1", "true", "yes", "да", "y")


def _read(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def load_item_scope(path: Optional[Path] = None) -> pd.DataFrame:
    return _read(path or ITEM_SCOPE)


def load_scope_rules(path: Optional[Path] = None) -> pd.DataFrame:
    return _read(path or SCOPE_RULES)


def _row_payload(source: pd.Series, origin: str) -> Dict[str, Any]:
    scope = str(source.get("scope", "")).strip() or "unclassified"
    payload = {
        "scope": scope,
        "classification_reason": str(source.get("classification_reason", "") or origin),
        "classification_source": str(source.get("source", "") or origin),
        "classification_comment": str(source.get("comment", "") or ""),
    }
    for col in FLAG_COLS:
        payload[col] = _flag(source.get(col, "1"), default=True)
    return payload


def _unclassified() -> Dict[str, Any]:
    payload = {
        "scope": "unclassified",
        "classification_reason": "Нет строки в справочнике и нет сработавшего правила",
        "classification_source": "unclassified",
        "classification_comment": "Не исключено автоматически. Заполните config/item_scope_classification.csv.",
    }
    for col in FLAG_COLS:
        payload[col] = True
    return payload


def _match_rule(name: str, level_0: str, level_1: str, rules: pd.DataFrame) -> Optional[pd.Series]:
    if rules.empty:
        return None
    n = norm_txt(name)
    l0 = norm_txt(level_0)
    l1 = norm_txt(level_1)
    for _, rule in rules.iterrows():
        if not _flag(rule.get("active", "1"), default=True):
            continue
        field = str(rule.get("match_field", "")).strip()
        value = norm_txt(rule.get("match_value", ""))
        if not value:
            continue
        if field == "level_0" and l0 == value:
            return rule
        if field == "level_1" and l1 == value:
            return rule
        if field == "name_equals" and n == value:
            return rule
        if field == "name_contains" and value in n:
            return rule
    return None


def classify_lines(
    df: pd.DataFrame,
    items: Optional[pd.DataFrame] = None,
    rules: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    out = df.copy()
    items = items if items is not None else load_item_scope()
    rules = rules if rules is not None else load_scope_rules()
    by_sku = {}
    by_name = {}
    if not items.empty:
        for _, row in items.iterrows():
            if not _flag(row.get("active", "1"), default=True):
                continue
            sku = str(row.get("sku", "")).strip()
            name = norm_txt(row.get("name", ""))
            if sku:
                by_sku[sku] = row
            if name:
                by_name[name] = row

    records = []
    for _, line in out.iterrows():
        art = str(line.get("артикул", "") or "").strip()
        name = norm_txt(line.get("наименование", ""))
        hit = by_sku.get(art) if art else None
        if hit is None and name:
            hit = by_name.get(name)
        if hit is not None:
            records.append(_row_payload(hit, "item_scope"))
            continue
        rule = _match_rule(
            str(line.get("наименование", "")),
            str(line.get("level_0", "") or ""),
            str(line.get("level_1", "") or ""),
            rules,
        )
        if rule is not None:
            records.append(_row_payload(rule, "scope_rule"))
            continue
        records.append(_unclassified())

    extra = pd.DataFrame(records)
    for col in extra.columns:
        out[col] = extra[col].values
    out["scope_label"] = out["scope"].map(_scope_label)
    out["in_financials"] = True
    out["is_non_core"] = out["scope"].isin(NON_CORE_SCOPES)
    return out


def _scope_label(scope: str) -> str:
    labels = {
        "own_production_ingredient": "Ингредиент СП",
        "own_production_raw_material": "Сырьё СП",
        "finished_goods": "Готовая продукция",
        "household_supply": "Хозтовары",
        "packaging": "Упаковка",
        "container": "Тара",
        "consumable": "Расходники",
        "equipment": "Оборудование",
        "other_non_core": "Прочее вне контура",
        "unclassified": "Не классифицировано",
    }
    return labels.get(str(scope), str(scope))


def household_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "is_non_core" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["is_non_core"]].copy()


def unclassified_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "scope" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["scope"] == "unclassified"].copy()


def production_mask(df: pd.DataFrame, flag: str) -> pd.Series:
    if flag not in df.columns:
        return pd.Series(True, index=df.index)
    return df[flag].astype(bool)
