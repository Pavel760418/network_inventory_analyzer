# -*- coding: utf-8 -*-
"""Объяснимый поиск кандидатов на пересорт.

Автоматическая находка всегда получает requires_manual_review и auto_apply=0.
Недостачу уменьшает только пара со статусом approved и auto_apply=1.
Семейства берутся из config/product_family_rules.csv, а не из догадки по любому общему слову.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from config.settings import PAIR_POOL_WARNING, matching_limits
from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import FAMILY_RULES

CUTS: Tuple[str, ...] = (
    "без кожи",
    "с костью",
    "стейк",
    "филе",
    "фарш",
    "тушка",
    "котлета",
)
STATES: Tuple[Tuple[str, str], ...] = (
    ("заморож", "замороженный"),
    ("охлажд", "охлажденный"),
    ("охл", "охлажденный"),
    ("копчен", "копченый"),
    ("солен", "соленый"),
    ("вялен", "вяленый"),
    ("свеж", "свежий"),
    ("маринован", "маринованный"),
)
ABBREVIATIONS = {
    "п/ф": "полуфабрикат",
    "зам": "замороженный",
    "охл": "охлажденный",
}

PROTECTED_APPROVALS = {"approved", "rejected", "expired", "отклонено"}


def normalize_product_name(name: str) -> str:
    text = norm_txt(name)
    for src, dst in ABBREVIATIONS.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def _weight_to_grams(value: float, unit: str) -> Optional[float]:
    if unit in ("г", "гр"):
        return value
    if unit == "кг":
        return value * 1000
    if unit == "мл":
        return value
    if unit == "л":
        return value * 1000
    return None


def parse_product(name: str, sku: str = "") -> Dict[str, Any]:
    normalized = normalize_product_name(name)
    cut = next((item for item in CUTS if item in normalized), "")
    state = ""
    for needle, label in STATES:
        if needle in normalized:
            state = label
            break
    weight = None
    unit = ""
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(кг|гр|г|мл|л)\b", normalized)
    if match:
        weight = _weight_to_grams(float(match.group(1).replace(",", ".")), match.group(2))
        unit = "г" if match.group(2) in ("г", "гр", "кг") else "мл"
    elif re.search(r"\bшт\b", normalized):
        unit = "шт"
    return {
        "raw": str(name).strip(),
        "sku": str(sku or "").strip(),
        "normalized": normalized,
        "cut": cut,
        "state": state,
        "weight": weight,
        "unit": unit or "не указана",
    }


def load_family_rules(path: Optional[Path] = None) -> pd.DataFrame:
    file = path or FAMILY_RULES
    if not file.is_file():
        return pd.DataFrame()
    return pd.read_csv(file, dtype=str).fillna("")


def _active(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "active" not in frame.columns:
        return frame
    mask = frame["active"].astype(str).str.lower().isin(("1", "true", "yes", "да", "y"))
    return frame[mask]


def families_of(parsed: Dict[str, Any], rules: pd.DataFrame) -> List[str]:
    if rules.empty:
        return []
    found = []
    text = parsed["normalized"]
    for _, row in _active(rules).iterrows():
        if str(row.get("token_type", "token")) not in ("token", ""):
            continue
        token = norm_txt(row.get("token_or_sku", ""))
        if token and token in text:
            family = str(row.get("family_id", "")).strip()
            if family and family not in found:
                found.append(family)
    return found


def _family_flags(family_id: str, rules: pd.DataFrame) -> pd.Series:
    rows = _active(rules)
    rows = rows[rows["family_id"] == family_id]
    if rows.empty:
        return pd.Series(dtype=object)
    return rows.iloc[0]


def _flag(value: Any, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "да", "y")


def units_comparable(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    mass = {"г", "не указана"}
    volume = {"мл", "не указана"}
    if left["unit"] == right["unit"]:
        return True
    if left["unit"] in mass and right["unit"] in mass:
        return True
    if left["unit"] in volume and right["unit"] in volume:
        return True
    return False


def classify_pair(left: Dict[str, Any], right: Dict[str, Any], rules: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Вернуть описание связи либо None, если пару предлагать нельзя."""
    if left["normalized"] == right["normalized"] and left["sku"] == right["sku"]:
        return None
    left_families = families_of(left, rules)
    right_families = families_of(right, rules)
    shared = [item for item in left_families if item in right_families]
    same_sku = bool(left["sku"] and left["sku"] == right["sku"])
    if not shared and not same_sku:
        return None
    flags = _family_flags(shared[0], rules) if shared else pd.Series(dtype=object)
    requires_cut = _flag(flags.get("requires_same_cut", "1"), True) if shared else False
    requires_state = _flag(flags.get("requires_same_state", "1"), True) if shared else False
    requires_unit = _flag(flags.get("requires_same_unit", "1"), True) if shared else False
    conversion = _flag(flags.get("conversion_allowed", "0"), False)
    reasons: List[str] = []
    if shared:
        reasons.append(f"совместимое семейство {flags.get('family_name', shared[0])}")
    if same_sku:
        reasons.append(f"совпадает артикул {left['sku']}")

    cut_same = bool(left["cut"] and left["cut"] == right["cut"])
    cut_diff = bool(left["cut"] and right["cut"] and left["cut"] != right["cut"])
    if cut_same:
        reasons.append(f"одинаковая форма {left['cut']}")
    elif cut_diff:
        reasons.append(f"разная форма {left['cut']} и {right['cut']}: нужно технологическое подтверждение")
    else:
        reasons.append("форма в имени не указана")

    state_same = left["state"] == right["state"]
    if left["state"] or right["state"]:
        if state_same:
            reasons.append(f"совпадение состояния {left['state'] or 'не указано'}")
        else:
            reasons.append(f"разное состояние {left['state'] or 'не указано'} и {right['state'] or 'не указано'}")
    else:
        reasons.append("состояние не различается")

    comparable = units_comparable(left, right)
    if not comparable:
        return {
            "compatibility_level": "incompatible",
            "similarity_score": 0,
            "match_reason": "несопоставимые единицы измерения",
            "relationship_type": "requires_manual_review",
            "approval_status": "requires_manual_review",
            "auto_apply": "0",
            "propose": False,
        }
    reasons.append("единица сопоставима")
    weights_differ = (
        left["weight"] is not None
        and right["weight"] is not None
        and abs(left["weight"] - right["weight"]) > 1e-6
    )
    if weights_differ and not conversion:
        reasons.append("разная масса без разрешённого коэффициента пересчёта")
    elif weights_differ and conversion:
        reasons.append("разная масса при разрешённом пересчёте")

    if cut_diff and requires_cut:
        level = "weak"
        score = 45
    elif cut_diff:
        level = "weak"
        score = 49
    elif not comparable:
        level = "incompatible"
        score = 0
    elif same_sku and not cut_diff:
        level = "exact"
        score = 96
    elif cut_same and state_same and not weights_differ:
        level = "medium"
        score = 82
    elif cut_same:
        level = "medium"
        score = 70
    else:
        level = "weak"
        score = 55
    if level == "strong":
        level = "medium"
    if cut_diff:
        level = "weak"
        score = min(score, 49)
    relationship = "same_cut_or_format" if cut_same else "same_product_family"
    if same_sku and left["normalized"] != right["normalized"] and not cut_diff:
        relationship = "exact_substitution"
    return {
        "compatibility_level": level,
        "similarity_score": score,
        "match_reason": "; ".join(reasons),
        "relationship_type": relationship,
        "approval_status": "requires_manual_review",
        "auto_apply": "0",
        "propose": level != "incompatible",
        "product_family_a": flags.get("family_name", "") if shared else "",
        "product_family_b": flags.get("family_name", "") if shared else "",
        "conversion_factor": "1" if not weights_differ else "",
    }


def _as_records(products: Iterable[Any]) -> List[Dict[str, Any]]:
    records = []
    seen = set()
    for item in products:
        if isinstance(item, dict):
            parsed = parse_product(str(item.get("name", "")), str(item.get("sku", "")))
        else:
            parsed = parse_product(str(item))
        if not parsed["normalized"]:
            continue
        key = (parsed["normalized"], parsed["sku"])
        if key in seen:
            continue
        seen.add(key)
        records.append(parsed)
    return records


def suggest_related_pairs(
    products: Iterable[Any],
    rules: Optional[pd.DataFrame] = None,
    mode: Optional[str] = None,
    max_candidate_comparisons: Optional[int] = None,
    max_items_per_side: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rules = rules if rules is not None else load_family_rules()
    limits = matching_limits(mode, max_candidate_comparisons, max_items_per_side)
    records = _as_records(products)
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        for family in families_of(record, rules) or ["__no_family__"]:
            by_family.setdefault(family, []).append(record)
    sku_groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        if record["sku"]:
            sku_groups.setdefault(record["sku"], []).append(record)

    potential = 0
    considered = 0
    excluded_incompatible = 0
    excluded_by_limit = 0
    suggestions: List[Dict[str, Any]] = []
    seen_pairs = set()

    def _consume(group: Sequence[Dict[str, Any]], family_bucket: bool) -> None:
        nonlocal potential, considered, excluded_incompatible, excluded_by_limit
        unique = []
        local_seen = set()
        for record in group:
            marker = id(record)
            if marker in local_seen:
                continue
            local_seen.add(marker)
            unique.append(record)
        full = len(unique) * (len(unique) - 1) // 2
        potential += full
        capped = unique
        if family_bucket and len(unique) > limits["max_items_per_side"]:
            dropped = len(unique) - limits["max_items_per_side"]
            excluded_by_limit += dropped * (dropped - 1) // 2 + dropped * limits["max_items_per_side"]
            capped = unique[: limits["max_items_per_side"]]
        for left, right in itertools.combinations(capped, 2):
            if considered >= limits["max_candidate_comparisons"]:
                excluded_by_limit += 1
                continue
            considered += 1
            verdict = classify_pair(left, right, rules)
            if verdict is None or not verdict.get("propose", False):
                excluded_incompatible += 1
                continue
            key = tuple(sorted((left["normalized"], right["normalized"], left["sku"], right["sku"])))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            explanation = (
                f"Кандидат: {left['raw']} ↔ {right['raw']}. "
                f"Причина: {verdict['match_reason']}. "
                f"Оценка связи: {verdict['similarity_score']}/100. "
                "Статус: требует ручной проверки. "
                "Финансовое перекрытие не применено."
            )
            suggestions.append(
                {
                    "pair_id": f"CAND-{len(suggestions) + 1:04d}",
                    "product_a_id": left["sku"],
                    "product_a_name": left["raw"],
                    "product_b_id": right["sku"],
                    "product_b_name": right["raw"],
                    "product_family_a": verdict.get("product_family_a", ""),
                    "product_family_b": verdict.get("product_family_b", ""),
                    "cut_a": left["cut"],
                    "cut_b": right["cut"],
                    "state_a": left["state"],
                    "state_b": right["state"],
                    "unit_a": left["unit"],
                    "unit_b": right["unit"],
                    "conversion_factor": verdict.get("conversion_factor", ""),
                    "relationship_type": verdict["relationship_type"],
                    "compatibility_level": verdict["compatibility_level"],
                    "similarity_score": verdict["similarity_score"],
                    "match_reason": explanation,
                    "approval_status": "requires_manual_review",
                    "auto_apply": "0",
                    "active": "1",
                    "source": "product_family_rules",
                    "approved_by": "",
                    "approved_at": "",
                    "priority": "50",
                    "comment": "Сгенерированный кандидат. Не утверждён.",
                }
            )

    for family, group in by_family.items():
        if family == "__no_family__":
            continue
        _consume(group, True)
    for group in sku_groups.values():
        if len(group) > 1:
            _consume(group, False)

    limited = excluded_by_limit > 0
    stats = {
        "potential_rows": potential,
        "considered": considered,
        "excluded_incompatible": excluded_incompatible,
        "excluded_by_limit": excluded_by_limit,
        "suggested": len(suggestions),
        "approved": 0,
        "limited": limited,
        "mode": limits["mode"],
        "max_candidate_comparisons": limits["max_candidate_comparisons"],
        "max_items_per_side": limits["max_items_per_side"],
        "warning": PAIR_POOL_WARNING if limited else "",
        "completeness_text": (
            f"Полный список по расчётному пулу; поиск потенциальных связей ограничен параметром "
            f"{limits['max_candidate_comparisons']} сравнений и {limits['max_items_per_side']} позиций в семействе."
            if limited
            else "Поиск кандидатов выполнен по совместимым семействам без срабатывания лимита."
        ),
    }
    return pd.DataFrame(suggestions), stats


def _pair_key(row: pd.Series) -> Tuple[str, str]:
    left = normalize_product_name(str(row.get("product_a_name", "")))
    right = normalize_product_name(str(row.get("product_b_name", "")))
    return tuple(sorted((left, right)))


def merge_pair_catalog(existing: pd.DataFrame, suggested: pd.DataFrame) -> pd.DataFrame:
    """Новые кандидаты добавляются. approved и rejected повторная генерация не перетирает."""
    if suggested is None or suggested.empty:
        return existing.copy() if existing is not None else pd.DataFrame()
    if existing is None or existing.empty:
        return suggested.copy()
    base = existing.copy()
    index = {_pair_key(row): idx for idx, row in base.iterrows()}
    technical = [
        "similarity_score",
        "match_reason",
        "compatibility_level",
        "cut_a",
        "cut_b",
        "state_a",
        "state_b",
        "unit_a",
        "unit_b",
        "product_family_a",
        "product_family_b",
        "conversion_factor",
    ]
    extra = []
    for _, row in suggested.iterrows():
        key = _pair_key(row)
        if key not in index:
            extra.append(row)
            continue
        current = base.loc[index[key]]
        approval = str(current.get("approval_status", "")).strip().lower()
        if approval in PROTECTED_APPROVALS:
            continue
        for column in technical:
            if column in row.index and column in base.columns:
                base.at[index[key], column] = row[column]
    if extra:
        base = pd.concat([base, pd.DataFrame(extra)], ignore_index=True)
    cleaned = base.astype(object)
    return cleaned.where(cleaned.notna(), "")
