# -*- coding: utf-8 -*-
"""Полный Excel v2. Top-N только на листах резюме и дашборда."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Iterable, List

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config.settings import PAIR_POOL_WARNING
from src.excel.styles import ACCENT, BD, DF, HD, SF, SUM, WH, tc
from src.network_inventory_analyzer.category_reserve import METHOD

NAVY = PatternFill("solid", fgColor=ACCENT)
WHITE = Font(name="Calibri", bold=True, color=WH, size=10)
TITLE = Font(name="Calibri", bold=True, color=ACCENT, size=16)


def _sheet(wb: Workbook, name: str):
    safe = name[:31]
    ws = wb.create_sheet(safe)
    return ws


def _write_frame(ws, frame: pd.DataFrame, header_row: int = 4) -> int:
    data = frame if frame is not None else pd.DataFrame()
    if data is None or data.empty:
        tc(ws, header_row, 1, "Нет строк", None)
        return header_row
    view = data.copy()
    view.columns = [str(c)[:80] for c in view.columns]
    for col, column in enumerate(view.columns, 1):
        cell = ws.cell(header_row, col, column)
        cell.fill = NAVY
        cell.font = WHITE
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BD
    for r_idx, (_, row) in enumerate(view.iterrows(), header_row + 1):
        for c_idx, value in enumerate(row.tolist(), 1):
            if isinstance(value, (pd.Timestamp,)):
                value = str(value)
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except Exception:
                    value = str(value)
            cell = ws.cell(r_idx, c_idx, None if pd.isna(value) else value)
            cell.border = BD
            cell.font = Font(name="Calibri", size=10)
            if isinstance(value, float):
                cell.number_format = SUM
        if r_idx % 2 == 0:
            for c_idx in range(1, len(view.columns) + 1):
                if ws.cell(r_idx, c_idx).fill.fgColor is None or True:
                    pass
    last = header_row + len(view)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(view.columns))}{last}"
    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(max(len(view.columns), 1))}{last}"
    for col in range(1, min(len(view.columns), 12) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22
    return last


def _banner(ws, title: str, subtitle: str) -> None:
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = subtitle
    ws["A2"].font = Font(name="Calibri", size=10, color="595959")
    ws.row_dimensions[1].height = 24
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.tabColor = ACCENT
    ws.oddHeader.left.text = title
    ws.oddFooter.right.text = "Полный список, без обрезки Top-N"


def _table_sheet(wb, name: str, title: str, subtitle: str, frame: pd.DataFrame) -> None:
    ws = _sheet(wb, name)
    _banner(ws, title, subtitle)
    _write_frame(ws, frame)
    ws.sheet_view.zoomScale = 110


def export_workbook(bundle: Dict[str, Any]) -> bytes:
    wb = Workbook()
    default = wb.active
    wb.remove(default)

    kpi = bundle["kpi"]
    ws = _sheet(wb, "Резюме_для_руководителя")
    _banner(ws, "Резюме для руководителя", "Суммы в рублях. Хозтовары показаны отдельно и не вычтены из общих недостач.")
    cards = [
        ("Магазинов", kpi["stores"]),
        ("SKU", kpi["sku"]),
        ("Недостачи, ₽", kpi["shortage"]),
        ("Излишки, ₽", kpi["surplus"]),
        ("Неперекрытая недостача контура, ₽", kpi["uncovered"]),
        ("Резерв категорий, ₽", kpi["reserve"]),
        ("Оприходованные излишки, ₽", kpi["posted"]),
        ("Хозтовары: недостачи, ₽", kpi["household_shortage"]),
        ("Хозтовары: излишки, ₽", kpi["household_surplus"]),
        ("Магазин с наибольшими чистыми недостачами", kpi["risk_store"]),
    ]
    for i, (label, value) in enumerate(cards, 4):
        tc(ws, i, 1, label, HD, bold=True)
        ws.cell(i, 1).font = WHITE
        cell = ws.cell(i, 2, value)
        cell.border = BD
        if isinstance(value, float):
            cell.number_format = SUM
            cell.fill = DF if value and "недостач" in label.lower() else SF
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 28
    ws.cell(16, 1, "Ключевые выводы")
    ws.cell(16, 1).font = TITLE
    for i, item in enumerate(bundle.get("conclusions") or [], 17):
        ws.cell(i, 1, item["text"])
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=4)
        ws.row_dimensions[i].height = 28

    dash = _sheet(wb, "Дашборд_ключевые_риски")
    _banner(dash, "Дашборд ключевых рисков", "Top-10 только на этом листе. Полные списки — на отдельных листах.")
    top = bundle["shortages"]
    if "include_in_shortage_top" in bundle["lines"].columns:
        names = set(bundle["lines"].loc[bundle["lines"]["include_in_shortage_top"] == True, "наименование"])  # noqa: E712
        top = bundle["shortages"][bundle["shortages"]["наименование"].isin(names)]
    top10 = top.head(10)[["магазин", "наименование", "недостача_сумма"]] if not top.empty else top
    _write_frame(dash, top10)
    if not top10.empty:
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Top-10 недостач операционного контура, ₽"
        chart.y_axis.title = "Позиция"
        chart.x_axis.title = "Недостача, ₽"
        data = Reference(dash, min_col=3, min_row=4, max_row=4 + len(top10))
        cats = Reference(dash, min_col=2, min_row=5, max_row=4 + len(top10))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.shape = 4
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showVal = True
        chart.height = 8
        chart.width = 18
        dash.add_chart(chart, "E4")

    sheets = [
        ("Недостачи_полный_список", "Недостачи — полный список", "100% строк с недостачей, включая хозтовары.", bundle["shortages"]),
        ("Излишки_полный_список", "Излишки — полный список", "100% строк с излишком.", bundle["surpluses"]),
        ("Пересорты_полный_список", "Пересорты по справочнику", "Подтверждённые и кандидаты. Кандидат недостачу не уменьшает.", bundle["regrades"]),
        ("Перекрытия_полный_список", "Перекрытия v4 внутри магазина", "Действующий однородный алгоритм, без обрезки 500 строк.", bundle["legacy_overlap"]),
        ("Кандидаты_на_пересорт", "Кандидаты на пересорт", _candidate_subtitle(bundle), bundle["candidates"]),
        ("Оприход_излишки_Резюме", "Оприходованные излишки — резюме", "Полное имя листа в этой строке.", bundle["posted_summary"]),
        ("Оприход_излишки_Связанные", "Оприходованные излишки — связанные", "Группа A.", bundle["posted_linked"]),
        ("Оприход_излишки_Кандидаты", "Оприходованные излишки — кандидаты", "Группа B. Ущерб не уменьшается.", bundle["posted_candidates"]),
        ("Оприход_излишки_Несвязанные", "Оприходованные излишки — несвязанные", "Группа C.", bundle["posted_unlinked"]),
        ("Оприход_излишки_Гипотезы", "Оприходованные излишки — гипотезы причин", "Это гипотезы, не факты.", bundle["posted_hypotheses"]),
        ("Оприход_излишки_Полный", "Оприходованные излишки — полный список", "100% строк файла оприходования.", bundle["posted_full"]),
        ("Хозтовары_упаковка_тара", "Хозтовары, упаковка и тара", "Вне операционного рейтинга. Суммы сохранены.", bundle["household"]),
        ("Товары_без_классификации", "Товары без классификации", "Не исключены. Заполните справочник.", bundle["unclassified"]),
        ("Резерв_категорий_детализация", "Резерв категорий", METHOD, bundle["reserve"]),
        ("Рейтинг_магазинов_детализация", "Рейтинг магазинов — компоненты", "Сумма компонент сверяется с баллом.", bundle["rating_components"]),
        ("Аномалии_цен_полный_список", "Аномалии цен — полный список", "Все ценовые пары.", bundle["prices"]),
        ("Говядина_Резюме", "Говядина — резюме", "Только подтверждённые SKU в суммах резюме.", bundle["beef_summary"]),
        ("Говядина_Недостачи", "Говядина — недостачи", "Подтверждённый контур.", bundle["beef_shortages"]),
        ("Говядина_Излишки", "Говядина — излишки", "Подтверждённый контур.", bundle["beef_surpluses"]),
        ("Говядина_Пересорты_и_пары", "Говядина — пересорты и пары", "Пары, где одна сторона подтверждена.", bundle["beef_pairs"]),
        ("Говядина_Перекрытия", "Говядина — перекрытия", "Однородные перекрытия v4 по подтверждённым именам.", _beef_overlap(bundle)),
        ("Говядина_Аномалии_цен", "Говядина — аномалии цен", "Пары цен по подтверждённым именам.", bundle["beef_prices"]),
        ("Говядина_Оприход_излишки", "Говядина — оприходованные излишки", "Строки оприходования с подтверждённым именем.", _beef_posted(bundle)),
        ("Говядина_Полный_список", "Говядина — полный список", "Подтверждённые, спорные и предварительные.", bundle["beef_full"]),
        ("Полнота_выгрузки_и_контроль", "Полнота выгрузки и контроль", "OK означает равенство числа строк.", bundle["completeness"]),
        ("Лог_проверок", "Лог проверок", "Замечания валидации.", pd.DataFrame({"проверка": bundle["quality"]})),
    ]
    for name, title, subtitle, frame in sheets:
        _table_sheet(wb, name, title, subtitle, frame if isinstance(frame, pd.DataFrame) else pd.DataFrame())

    _methodology(wb)
    _rating_method(wb)
    _beef_method(wb)
    _contents(wb)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _candidate_subtitle(bundle: Dict[str, Any]) -> str:
    stats = bundle.get("pair_search") or {}
    base = "Кандидаты не уменьшают недостачу, пока approval_status не равен approved и auto_apply не включён."
    if stats.get("limited"):
        return f"{base} {PAIR_POOL_WARNING} {stats.get('completeness_text', '')}"
    return base


def _beef_overlap(bundle: Dict[str, Any]) -> pd.DataFrame:
    overlap = bundle.get("legacy_overlap", pd.DataFrame())
    full = bundle.get("beef_full", pd.DataFrame())
    if overlap is None or overlap.empty or full is None or full.empty:
        return pd.DataFrame()
    names = set(full.loc[full.get("beef_confirmed", False) == True, "наименование"].astype(str)) if "beef_confirmed" in full.columns else set()  # noqa: E712
    if not names or "недостача_товар" not in overlap.columns:
        return overlap.iloc[0:0]
    mask = overlap["недостача_товар"].astype(str).isin(names) | overlap["излишек_товар"].astype(str).isin(names)
    return overlap[mask].copy()


def _beef_posted(bundle: Dict[str, Any]) -> pd.DataFrame:
    posted = bundle.get("posted_full", pd.DataFrame())
    full = bundle.get("beef_full", pd.DataFrame())
    if posted is None or posted.empty or full is None or full.empty:
        return pd.DataFrame(columns=getattr(posted, "columns", []))
    names = set(full.loc[full["beef_confirmed"] == True, "наименование"].astype(str)) if "beef_confirmed" in full.columns else set()  # noqa: E712
    if not names or "Наименование" not in posted.columns:
        return posted.iloc[0:0]
    return posted[posted["Наименование"].astype(str).isin(names)].copy()


def _methodology(wb: Workbook) -> None:
    ws = _sheet(wb, "Методология")
    _banner(ws, "Методология", "Автоматически уменьшает недостачу только подтверждённая пара.")
    lines = [
        "1. Недостача строки = модуль отрицательной разницы количества и сумма недостачи из выгрузки. Формула v4 не менялась.",
        "2. Излишек строки = положительная разница. Формула v4 не менялась.",
        "3. Однородное перекрытие v4 ищет пары внутри одной category_group одного магазина и не расходует количество дважды.",
        "4. Пара справочника с типом requires_manual_review или без approved_by — кандидат. Она не уменьшает недостачу.",
        "5. Пара уменьшает недостачу только если тип связи из списка прямых замен и заполнено approved_by.",
        "6. Резерв категории = max(min(недостача, излишки) − факт перекрытия, 0). Это не экономия.",
        "7. Рейтинг: балл v4 только по строкам include_in_store_rating=1. Выше балл — лучше.",
        "8. Хозтовары, тара, упаковка, расходники остаются в общих суммах и в своём листе.",
        "9. Говядина в суммах блока — только active=1 в config/beef_scope.csv.",
        "10. Гипотеза причины оприходования не является установленным фактом.",
        METHOD,
    ]
    for i, line in enumerate(lines, 4):
        ws.cell(i, 1, line)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=6)
        ws.row_dimensions[i].height = 32
    ws.column_dimensions["A"].width = 40


def _rating_method(wb: Workbook) -> None:
    ws = _sheet(wb, "Методология_рейтинга_магазинов")
    _banner(ws, "Методология рейтинга магазинов", "Веса v4 сохранены. Новые показатели добавлены с весом 0.")
    rows = [
        ["Показатель", "Формула", "Источник", "Вес", "Направление", "Нормализация", "Почему включён", "Исключения", "Пример"],
        ["Shrinkage", "чистые недостачи / сумма учётная × 100", "строки рейтинга", "0.35", "меньше лучше", "percentile, инверсия", "доля потерь к учётной сумме", "хозтовары вне контура", "1000 / 10000 = 10%"],
        ["Восстановление", "перекрытие / недостачи × 100", "overlap v4 + подтверждённые пары в чистых недостачах через overlap", "0.25", "больше лучше", "percentile", "показывает, сколько недостачи объяснено", "кандидаты не входят", "200 / 1000 = 20%"],
        ["Чистые недостачи", "max(недостача − перекрытие, 0)", "магазин", "0.25", "меньше лучше", "percentile, инверсия", "основной операционный риск", "хозтовары", "1000 − 200 = 800"],
        ["SKU с расхождениями", "число строк с излишком или недостачей", "магазин", "0.15", "меньше лучше", "percentile, инверсия", "ширина проблемы", "хозтовары", "3 SKU"],
        ["Излишки", "сумма излишков", "магазин", "0", "справочно", "нет", "в формуле v4 веса нет, коэффициент не выдумывался", "не влияет на балл", "вес 0"],
        ["Аномалии цен", "число пар", "price_compare", "0", "справочно", "нет", "финансовый эффект v4 не задан", "не влияет на балл", "вес 0"],
        ["Резерв", "см. методологию резерва", "категории", "0", "справочно", "нет", "резерв не является баллом экономии", "не влияет на балл", "вес 0"],
    ]
    for r, row in enumerate(rows, 4):
        for c, value in enumerate(row, 1):
            cell = ws.cell(r, c, value)
            cell.border = BD
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            if r == 4:
                cell.fill = NAVY
                cell.font = WHITE
        ws.row_dimensions[r].height = 36
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = 24
    ws.cell(14, 1, "Равенство баллов разрешается по имени магазина. Магазин без строк контура в рейтинг не попадает.")
    ws.merge_cells("A14:F14")


def _beef_method(wb: Workbook) -> None:
    ws = _sheet(wb, "Говядина_Методология")
    _banner(ws, "Методология говядины", "Слово «говядина» в имени само по себе сумму не подтверждает.")
    text = [
        "Подтверждено: active=1 в config/beef_scope.csv.",
        "На проверке: строка справочника с active=0.",
        "Предварительно классифицировано: в имени есть «говяд», строки справочника нет. В суммы резюме не входит.",
        "Сумма недостач блока равна сумме недостач подтверждённых строк и сходится с фильтром полного списка.",
    ]
    for i, line in enumerate(text, 4):
        ws.cell(i, 1, line)
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=4)


def _contents(wb: Workbook) -> None:
    ws = _sheet(wb, "Содержание")
    wb.move_sheet(ws, offset=-len(wb.sheetnames) + 1)
    _banner(ws, "Содержание", "Переход по листам.")
    for i, name in enumerate(wb.sheetnames, 4):
        cell = ws.cell(i, 1, name)
        cell.hyperlink = f"#'{name}'!A1"
        cell.style = "Hyperlink"
    ws.column_dimensions["A"].width = 42
    ws.freeze_panes = "A4"


def assert_no_excel_errors(raw: bytes) -> List[str]:
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(raw))
    bad = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith(("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A")):
                    bad.append(f"{ws.title}!{cell.coordinate}")
    return bad
