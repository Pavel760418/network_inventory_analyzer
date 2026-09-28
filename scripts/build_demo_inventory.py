# -*- coding: utf-8 -*-
"""Собрать синтетическую выгрузку инвентаризации для демо и тестов.

Файл не содержит реальных магазинов, SKU и финансовых результатов сети.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data" / "demo_inventory_synthetic.xlsx"


def _row(name, book_qty, fact_qty, diff, book_sum, fact_sum, sum_diff, surplus_sum, shortage_sum):
    return [name, book_qty, fact_qty, diff, book_sum, fact_sum, sum_diff, surplus_sum, shortage_sum]


def build(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "TDSheet"
    ws.append(
        [
            "Документ.Подразделение",
            "Количество книжное",
            "Количество фактическое",
            "Отклонение количества",
            "Сумма книжная нормативная",
            "Сумма фактическая нормативная",
            "Сумма разница",
            "Сумма излишек",
            "Сумма недостача",
        ]
    )
    ws.append([""] * 9)
    ws.append([""] * 9)
    ws.append(_row("Сеть Демо", 0, 0, 0, 0, 0, 0, 0, 0))

    def store(name: str) -> None:
        ws.append(_row(name, 0, 0, 0, 0, 0, 0, 0, 0))
        ws.row_dimensions[ws.max_row].outlineLevel = 0

    def doc(text: str) -> None:
        ws.append(_row(text, 0, 0, 0, 0, 0, 0, 0, 0))
        ws.row_dimensions[ws.max_row].outlineLevel = 1

    def sku(*values) -> None:
        ws.append(_row(*values))
        ws.row_dimensions[ws.max_row].outlineLevel = 2

    store("Магазин Альфа")
    doc("Инвентаризация Д-1 от 01.09.2026")
    # недостача семги: 4 кг * 1000
    sku("Семга стейк", 10, 6, -4, 10000, 6000, -4000, 0, 4000)
    # излишек форели: 4 кг * 900
    sku("Форель стейк", 5, 9, 4, 4500, 8100, 3600, 3600, 0)
    sku("Пакет майка", 100, 80, -20, 1000, 500, -500, 0, 500)
    sku("Говядина вырезка demo", 8, 4, -4, 4000, 2000, -2000, 0, 2000)
    sku("Салат овощной СП demo", 3, 5, 2, 900, 1700, 800, 800, 0)
    sku("Позиция без класса demo", 2, 1, -1, 200, 100, -100, 0, 100)

    store("Магазин Бета")
    doc("Инвентаризация Д-2 от 15.09.2026")
    sku("Говядина вырезка demo", 2, 4, 2, 1000, 1500, 500, 500, 0)
    sku("Контейнер пластиковый", 40, 20, -20, 800, 500, -300, 0, 300)
    sku("Семга стейк", 4, 2, -2, 4000, 3000, -1000, 0, 1000)
    sku("Бульон говяжий demo", 1, 0, -1, 150, 0, -150, 0, 150)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


if __name__ == "__main__":
    print(build())
