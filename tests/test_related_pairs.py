# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from src.network_inventory_analyzer.related_pairs import find_pair_for_names, load_pairs, pair_decision
from src.network_inventory_analyzer.regrading import build_dictionary_regrades
from src.network_inventory_analyzer.settings import STATUS_AUTO, STATUS_REVIEW


def _lines():
    return pd.DataFrame(
        {
            "магазин": ["А", "А", "А"],
            "дата_док": ["2026-09-01", "2026-09-01", "2026-09-01"],
            "наименование": ["Семга стейк", "Форель стейк", "Семга стейк"],
            "артикул": ["s", "f", "s2"],
            "category_group": ["рыба", "рыба", "рыба"],
            "излишек_кол": [0.0, 4.0, 0.0],
            "излишек_сумма": [0.0, 3600.0, 0.0],
            "недостача_кол": [4.0, 0.0, 2.0],
            "недостача_сумма": [4000.0, 0.0, 2000.0],
            "include_in_regrading": [True, True, True],
        }
    )


def test_dictionary_detects_salmon_trout_example():
    pairs = load_pairs()
    found = find_pair_for_names("Семга стейк", "Форель стейк", "", "", pairs)
    assert found is not None
    assert found["pair_id"] == "P-DEMO-001"
    assert pair_decision(found) == STATUS_REVIEW


def test_self_pair_is_not_used():
    pairs = pd.DataFrame(
        [
            {
                "pair_id": "SELF",
                "product_a_id": "",
                "product_a_name": "Семга стейк",
                "product_b_id": "",
                "product_b_name": "Семга стейк",
                "relationship_type": "exact_substitution",
                "match_level": "name_normalized",
                "priority": "1",
                "active": "1",
                "approved_by": "тест",
                "source": "test",
            }
        ]
    )
    assert find_pair_for_names("Семга стейк", "Семга стейк", "", "", pairs) is None


def test_review_candidate_does_not_reduce_shortage():
    regrades = build_dictionary_regrades(_lines(), load_pairs())
    assert not regrades.empty
    assert set(regrades["статус"]) == {STATUS_REVIEW}
    assert regrades["уменьшает_недостачу"].eq(False).all()
    assert float(regrades["перекрытие_сум"].sum()) > 0


def test_auto_pair_does_not_reuse_surplus_above_quantity():
    pairs = pd.DataFrame(
        [
            {
                "pair_id": "AUTO",
                "product_a_id": "",
                "product_a_name": "Семга стейк",
                "product_b_id": "",
                "product_b_name": "Форель стейк",
                "relationship_type": "exact_substitution",
                "match_level": "name_normalized",
                "priority": "1",
                "active": "1",
                "approved_by": "комиссия",
                "source": "test",
            }
        ]
    )
    regrades = build_dictionary_regrades(_lines(), pairs)
    applied = regrades[regrades["статус"] == STATUS_AUTO]
    assert float(applied["перекрытие_кол"].sum()) <= 4.0 + 1e-6
    by_short = applied.groupby("недостача_sku")["перекрытие_кол"].sum()
    assert float(by_short.get("Семга стейк", 0)) <= 6.0 + 1e-6
    assert abs(float(applied["перекрытие_сум"].sum()) - float(applied.groupby("pair_id")["перекрытие_сум"].sum().sum())) < 1e-6
