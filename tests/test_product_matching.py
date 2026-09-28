# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from src.network_inventory_analyzer.product_matching import (
    classify_pair,
    merge_pair_catalog,
    parse_product,
    suggest_related_pairs,
)
from src.network_inventory_analyzer.regrading import build_dictionary_regrades
from src.network_inventory_analyzer.settings import STATUS_AUTO, STATUS_REVIEW


def test_salmon_trout_is_review_candidate_from_family_rules():
    suggested, stats = suggest_related_pairs(["Семга стейк", "Форель стейк"])
    assert len(suggested) == 1
    row = suggested.iloc[0]
    assert row["approval_status"] == "requires_manual_review"
    assert str(row["auto_apply"]) in ("0", "false", "False")
    assert "лососевые" in row["match_reason"]
    assert int(row["similarity_score"]) >= 80
    assert stats["approved"] == 0
    assert stats["limited"] is False


def test_candidate_does_not_reduce_shortage():
    lines = pd.DataFrame(
        {
            "магазин": ["А", "А"],
            "дата_док": ["2026-09-01", "2026-09-01"],
            "наименование": ["Семга стейк", "Форель стейк"],
            "артикул": ["s", "f"],
            "category_group": ["рыба", "рыба"],
            "излишек_кол": [0.0, 4.0],
            "излишек_сумма": [0.0, 3600.0],
            "недостача_кол": [4.0, 0.0],
            "недостача_сумма": [4000.0, 0.0],
            "include_in_regrading": [True, True],
        }
    )
    suggested, _stats = suggest_related_pairs(lines["наименование"])
    regrades = build_dictionary_regrades(lines, suggested)
    assert not regrades.empty
    assert set(regrades["статус"]) == {STATUS_REVIEW}
    assert regrades["уменьшает_недостачу"].eq(False).all()


def test_approved_auto_apply_can_cover_within_quantity():
    pairs = pd.DataFrame(
        [
            {
                "pair_id": "OK",
                "product_a_id": "",
                "product_a_name": "Семга стейк",
                "product_b_id": "",
                "product_b_name": "Форель стейк",
                "relationship_type": "exact_substitution",
                "priority": "1",
                "active": "1",
                "approval_status": "approved",
                "auto_apply": "1",
                "approved_by": "комиссия",
                "source": "test",
            }
        ]
    )
    lines = pd.DataFrame(
        {
            "магазин": ["А", "А"],
            "дата_док": ["2026-09-01", "2026-09-01"],
            "наименование": ["Семга стейк", "Форель стейк"],
            "артикул": ["s", "f"],
            "излишек_кол": [0.0, 4.0],
            "излишек_сумма": [0.0, 3600.0],
            "недостача_кол": [4.0, 0.0],
            "недостача_сумма": [4000.0, 0.0],
            "include_in_regrading": [True, True],
        }
    )
    regrades = build_dictionary_regrades(lines, pairs)
    assert set(regrades["статус"]) == {STATUS_AUTO}
    assert float(regrades["перекрытие_кол"].sum()) <= 4.0
    assert float(regrades["перекрытие_кол"].sum()) <= float(lines["недостача_кол"].sum())
    assert abs(float(regrades["перекрытие_сум"].sum()) - float(regrades["перекрытие_сум"].sum())) < 1e-6


def test_steak_and_fillet_are_not_strong_or_approved():
    suggested, _stats = suggest_related_pairs(["Семга стейк", "Семга филе"])
    assert len(suggested) == 1
    row = suggested.iloc[0]
    assert row["compatibility_level"] == "weak"
    assert row["compatibility_level"] != "strong"
    assert row["approval_status"] == "requires_manual_review"


def test_incompatible_units_are_not_proposed():
    from src.network_inventory_analyzer.product_matching import load_family_rules

    rules = load_family_rules()
    verdict = classify_pair(parse_product("Семга стейк 1 кг"), parse_product("Семга стейк 10 шт"), rules)
    assert verdict is not None
    assert verdict["compatibility_level"] == "incompatible"
    assert verdict["propose"] is False
    suggested, _stats = suggest_related_pairs(["Семга стейк 1 кг", "Семга стейк 10 шт"])
    assert suggested.empty


def test_rejected_status_survives_regeneration():
    suggested, _stats = suggest_related_pairs(["Семга стейк", "Форель стейк"])
    manual = suggested.copy()
    manual.loc[0, "approval_status"] = "rejected"
    manual.loc[0, "approved_by"] = "технолог"
    again, _stats = suggest_related_pairs(["Семга стейк", "Форель стейк"])
    merged = merge_pair_catalog(manual, again)
    assert len(merged) == 1
    assert merged.iloc[0]["approval_status"] == "rejected"


def test_limit_is_reported_and_not_called_complete_search():
    names = [f"Семга вид{i} стейк" for i in range(6)]
    rules = pd.DataFrame(
        [
            {
                "family_id": "FAM-SALMON",
                "family_name": "лососевые",
                "token_or_sku": "семга",
                "token_type": "token",
                "related_family_id": "",
                "relationship_type": "same_product_family",
                "compatibility_level": "medium",
                "requires_same_cut": "1",
                "requires_same_state": "1",
                "requires_same_unit": "1",
                "conversion_allowed": "0",
                "default_approval_status": "requires_manual_review",
                "source": "test",
                "comment": "",
                "active": "1",
            }
        ]
    )
    _suggested, stats = suggest_related_pairs(names, rules, max_items_per_side=2, max_candidate_comparisons=100)
    assert stats["excluded_by_limit"] > 0
    assert stats["limited"] is True
    assert "ограничен параметром" in stats["completeness_text"]
    assert "100%" not in stats["completeness_text"]
