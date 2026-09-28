# -*- coding: utf-8 -*-
"""Пути и константы контура v2. Абсолютные пути пользователя не задаются."""
from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PACKAGE_ROOT / "config"
SAMPLE_DIR = PACKAGE_ROOT / "sample_data"

SCOPE_RULES = CONFIG_DIR / "scope_rules.csv"
ITEM_SCOPE = CONFIG_DIR / "item_scope_classification.csv"
RELATED_PAIRS = CONFIG_DIR / "related_product_pairs.csv"
BEEF_SCOPE = CONFIG_DIR / "beef_scope.csv"
DEMO_INVENTORY = SAMPLE_DIR / "demo_inventory_synthetic.xlsx"

NON_CORE_SCOPES = frozenset(
    {
        "household_supply",
        "packaging",
        "container",
        "consumable",
        "equipment",
        "other_non_core",
    }
)

AUTO_PAIR_TYPES = frozenset(
    {
        "exact_substitution",
        "same_raw_material",
        "same_cut_or_format",
        "same_product_family",
        "production_ingredient_substitution",
    }
)

STATUS_AUTO = "автоматически подтверждено"
STATUS_REVIEW = "требует ручной проверки"
STATUS_REJECTED = "отклонено"

HYPOTHESIS_PREFIX = "Гипотеза причины / требуется проверка"

# Действующая формула рейтинга v4. Веса не меняются без согласования.
RATING_WEIGHTS = {
    "shrinkage_pct": 0.35,
    "recovery_pct": 0.25,
    "чистые_недостачи": 0.25,
    "sku_с_расх": 0.15,
}
