# -*- coding: utf-8 -*-
from pathlib import Path

from src.network_inventory_analyzer.ui_helpers import TABS, shown_frame
import pandas as pd


def test_tabs_cover_required_sections():
    needed = [
        "Главная",
        "Недостачи",
        "Излишки",
        "Пересорты и перекрытия",
        "Оприходованные излишки",
        "Говядина",
        "Рейтинг магазинов",
        "Резерв категорий",
        "Хозтовары и упаковка",
        "Аномалии цен",
        "Полные списки и экспорт",
        "Контроль качества",
        "Методология",
        "Инструкция",
    ]
    assert needed == TABS


def test_shown_counter():
    df = pd.DataFrame({"a": range(10)})
    part, shown, total = shown_frame(df, show_all=False, limit=3)
    assert shown == 3 and total == 10 and len(part) == 3
    part, shown, total = shown_frame(df, show_all=True, limit=3)
    assert shown == total == 10


def test_app_parses():
    import ast

    ast.parse(Path("app.py").read_text(encoding="utf-8"))
