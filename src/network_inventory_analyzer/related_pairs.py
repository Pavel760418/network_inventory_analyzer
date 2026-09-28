# -*- coding: utf-8 -*-
"""Справочник допустимых пар. Совпадение только по точному нормализованному имени или id.

Случайное пересечение слов не создаёт пару.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import (
    AUTO_PAIR_TYPES,
    RELATED_PAIRS,
    STATUS_AUTO,
    STATUS_REJECTED,
    STATUS_REVIEW,
)
from src.network_inventory_analyzer.validators import validate_pairs


def load_pairs(path: Optional[Path] = None) -> pd.DataFrame:
    file = path or RELATED_PAIRS
    if not file.is_file():
        return pd.DataFrame()
    df = pd.read_csv(file, dtype=str).fillna("")
    return df


def pair_decision(row: pd.Series) -> str:
    active = str(row.get("active", "1")).strip().lower() in ("1", "true", "yes", "да", "y")
    if not active:
        return STATUS_REJECTED
    rel = str(row.get("relationship_type", "")).strip()
    approved = str(row.get("approved_by", "")).strip()
    if rel == "requires_manual_review" or not approved or rel not in AUTO_PAIR_TYPES:
        if rel == "requires_manual_review" or not approved:
            return STATUS_REVIEW
        return STATUS_REVIEW
    return STATUS_AUTO


def _sides(row: pd.Series) -> List[Dict[str, str]]:
    return [
        {
            "id": str(row.get("product_a_id", "")).strip(),
            "name": norm_txt(row.get("product_a_name", "")),
            "raw": str(row.get("product_a_name", "")).strip(),
        },
        {
            "id": str(row.get("product_b_id", "")).strip(),
            "name": norm_txt(row.get("product_b_name", "")),
            "raw": str(row.get("product_b_name", "")).strip(),
        },
    ]


def find_pair_for_names(
    name_left: str,
    name_right: str,
    art_left: str,
    art_right: str,
    pairs: pd.DataFrame,
) -> Optional[pd.Series]:
    """Вернуть строку справочника, если левая и правая позиции — две стороны одной пары."""
    if pairs is None or pairs.empty:
        return None
    left_name = norm_txt(name_left)
    right_name = norm_txt(name_right)
    if not left_name or not right_name or left_name == right_name:
        return None
    left_art = str(art_left or "").strip()
    right_art = str(art_right or "").strip()
    best = None
    best_priority = 10**9
    for _, row in pairs.iterrows():
        sides = _sides(row)
        if not sides[0]["name"] and not sides[0]["id"]:
            continue
        if not sides[1]["name"] and not sides[1]["id"]:
            continue
        if sides[0]["name"] and sides[0]["name"] == sides[1]["name"]:
            continue

        def hit(side: Dict[str, str], name: str, art: str) -> bool:
            if side["id"] and art and side["id"] == art:
                return True
            return bool(side["name"]) and side["name"] == name

        direct = hit(sides[0], left_name, left_art) and hit(sides[1], right_name, right_art)
        reverse = hit(sides[1], left_name, left_art) and hit(sides[0], right_name, right_art)
        if not (direct or reverse):
            continue
        try:
            priority = int(float(row.get("priority") or 100))
        except ValueError:
            priority = 100
        if priority < best_priority:
            best = row
            best_priority = priority
    return best


def pair_issues(pairs: pd.DataFrame) -> List[str]:
    return validate_pairs(pairs)
