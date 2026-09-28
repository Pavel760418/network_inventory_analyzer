# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from src.network_inventory_analyzer.scope_classifier import classify_lines, household_frame


def test_household_excluded_from_rating_but_kept_in_money():
    df = pd.DataFrame(
        {
            "артикул": ["", ""],
            "наименование": ["Пакет майка", "Семга стейк"],
            "level_0": ["", ""],
            "level_1": ["", ""],
            "недостача_сумма": [500.0, 4000.0],
            "излишек_сумма": [0.0, 0.0],
        }
    )
    out = classify_lines(df)
    package = out[out["наименование"] == "Пакет майка"].iloc[0]
    fish = out[out["наименование"] == "Семга стейк"].iloc[0]
    assert package["scope"] == "packaging"
    assert bool(package["include_in_store_rating"]) is False
    assert bool(fish["include_in_store_rating"]) is True
    household = household_frame(out)
    assert float(household["недостача_сумма"].sum()) == 500.0
    assert float(out["недостача_сумма"].sum()) == 4500.0


def test_unclassified_is_not_dropped():
    df = pd.DataFrame(
        {
            "артикул": [""],
            "наименование": ["Позиция без класса demo"],
            "level_0": [""],
            "level_1": [""],
            "недостача_сумма": [100.0],
            "излишек_сумма": [0.0],
        }
    )
    out = classify_lines(df)
    assert out.iloc[0]["scope"] == "unclassified"
    assert bool(out.iloc[0]["include_in_store_rating"]) is True
