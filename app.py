# -*- coding: utf-8 -*-
"""Анализ инвентаризации собственного производства.

Пользовательские файлы живут только в текущей сессии и не пишутся в репозиторий.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import PAIR_POOL_WARNING
from src.network_inventory_analyzer import __version__
from src.network_inventory_analyzer.category_reserve import METHOD
from src.network_inventory_analyzer.excel_exporter import export_workbook
from src.network_inventory_analyzer.pipeline import analyze
from src.network_inventory_analyzer.settings import DEMO_INVENTORY, RATING_WEIGHTS
from src.network_inventory_analyzer.store_rating import why_store
from src.network_inventory_analyzer.ui_helpers import KPI_HELP, TABS, shown_frame

st.set_page_config(
    page_title="Анализ инвентаризации собственного производства",
    page_icon=":material/inventory:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _save_upload(uploaded) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.write(uploaded.getvalue())
    tmp.close()
    return Path(tmp.name)


def _load_bundle(inventory: Path, capitalization: Path | None, period: int, mode: str, comparisons: int, per_side: int):
    return analyze(
        inventory,
        period_days=period,
        capitalization_path=capitalization,
        matching_mode=mode,
        max_candidate_comparisons=comparisons,
        max_items_per_side=per_side,
    )


def _filters(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df
    store_col = "магазин" if "магазин" in work.columns else ("Магазин" if "Магазин" in work.columns else None)
    if store_col:
        stores = sorted(work[store_col].dropna().astype(str).unique())
        picked = st.multiselect("Магазин", stores, key=f"{key}-store")
        if picked:
            work = work[work[store_col].astype(str).isin(picked)]
    query = st.text_input("Поиск по таблице", key=f"{key}-q")
    if query:
        mask = work.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
        work = work[mask]
    return work


def _show_table(df: pd.DataFrame, key: str, name: str) -> None:
    show_all = st.checkbox("Показать все", key=f"{key}-all")
    if show_all and df is not None and len(df) > 5000:
        st.warning(f"В выборке {len(df)} строк. Отображение может занять время. Полный файл лучше скачать.")
    part, shown, total = shown_frame(df, show_all)
    st.caption(f"Показано {shown} из {total} строк")
    st.dataframe(part, use_container_width=True, hide_index=True)
    if df is not None and not df.empty:
        st.download_button(
            f"Скачать полный CSV — {name}",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{name}.csv",
            mime="text/csv",
            key=f"{key}-csv",
        )


def _bar(df: pd.DataFrame, label: str, value: str, title: str) -> None:
    if df is None or df.empty or label not in df.columns or value not in df.columns:
        st.info("Недостаточно данных для графика.")
        return
    chart = df[[label, value]].head(10).set_index(label)
    st.caption(title)
    st.bar_chart(chart)


def _kpi_card(label: str, value, help_key: str) -> None:
    st.metric(label, value, help=KPI_HELP.get(help_key, ""))


def page_home(bundle) -> None:
    kpi = bundle["kpi"]
    c = st.columns(5)
    with c[0]:
        _kpi_card("Магазинов в анализе", kpi["stores"], "stores")
    with c[1]:
        _kpi_card("SKU в анализе", kpi["sku"], "sku")
    with c[2]:
        _kpi_card("Недостачи, ₽", f"{kpi['shortage']:,.2f}", "shortage")
    with c[3]:
        _kpi_card("Излишки, ₽", f"{kpi['surplus']:,.2f}", "surplus")
    with c[4]:
        _kpi_card("Неперекрытая недостача, ₽", f"{kpi['uncovered']:,.2f}", "uncovered")
    c2 = st.columns(5)
    with c2[0]:
        _kpi_card("Резерв категорий, ₽", f"{kpi['reserve']:,.2f}", "reserve")
    with c2[1]:
        _kpi_card("Оприходованные излишки, ₽", f"{kpi['posted']:,.2f}", "posted")
    with c2[2]:
        _kpi_card("Хозтовары: недостачи, ₽", f"{kpi['household_shortage']:,.2f}", "household_shortage")
    with c2[3]:
        _kpi_card("Хозтовары: излишки, ₽", f"{kpi['household_surplus']:,.2f}", "household_shortage")
    with c2[4]:
        _kpi_card("Магазин с наибольшим риском", kpi["risk_store"] or "—", "risk_store")
    st.caption(
        f"Аномалии цен: {kpi['price_pairs']} пар. "
        "Финансовый эффект отклонения цены отдельной суммой в действующей формуле не считается."
    )
    with st.expander("Как рассчитан резерв?"):
        st.write(METHOD)
    st.subheader("Ключевые выводы и действия")
    for item in bundle["conclusions"]:
        st.write(f"{item['text']}  ·  вкладка «{item['tab']}»")

    st.subheader("Top-10")
    op_names = set(
        bundle["lines"].loc[bundle["lines"]["include_in_shortage_top"] == True, "наименование"].astype(str)  # noqa: E712
    )
    op_short = bundle["shortages"][bundle["shortages"]["наименование"].astype(str).isin(op_names)].head(10)
    blocks = [
        ("Неперекрытые недостачи", op_short, "наименование", "недостача_сумма", "Недостачи"),
        ("Кандидаты на пересорт", bundle["candidates"].head(10) if bundle["candidates"] is not None else bundle["candidates"], "недостача_sku", "перекрытие_сум", "Пересорты и перекрытия"),
        ("Несвязанные оприходованные излишки", bundle["posted_unlinked"].head(10) if not bundle["posted_unlinked"].empty else bundle["posted_unlinked"], "Наименование", "Сумма излишка", "Оприходованные излишки"),
        ("Аномалии цен", bundle["prices"].head(10) if bundle["prices"] is not None else bundle["prices"], "наименование", "разница_цены_%", "Аномалии цен"),
    ]
    for title, frame, label, value, _tab in blocks:
        st.markdown(f"**{title}**")
        if frame is None or frame.empty:
            st.info("Недостаточно данных для вывода.")
            continue
        _bar(frame, label, value, f"{title}, полный набор больше Top-10")
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.caption(f"В блоке приоритизации до 10 строк. Полный список: {len(frame) if title.startswith('Неперекрытые') else 'см. вкладку'}.")

    if not bundle["rating"].empty:
        st.markdown("**Магазины по чистым недостачам**")
        risk = bundle["rating"].sort_values("чистые_недостачи", ascending=False).head(10)
        _bar(risk, "магазин", "чистые_недостачи", "Чистые недостачи операционного контура, ₽")
        st.dataframe(risk[["магазин", "место", "store_score", "чистые_недостачи"]], use_container_width=True, hide_index=True)
    if not bundle["reserve"].empty:
        st.markdown("**Категории по резерву**")
        _bar(bundle["reserve"].head(10), "Категория", "Резерв, ₽", "Резерв не является экономией")
    beef = bundle["beef_shortages"]
    st.markdown("**Говядина: подтверждённые недостачи**")
    if beef is None or beef.empty:
        st.info("Недостаточно данных для вывода по подтверждённой говядине.")
    else:
        _bar(beef.head(10), "наименование", "недостача_сумма", "Только active=1 в справочнике говядины")
        st.dataframe(beef.head(10), use_container_width=True, hide_index=True)


def page_rating(bundle) -> None:
    st.subheader("Как формируется рейтинг")
    st.write(
        "Балл v4 = shrinkage×0.35 + восстановление×0.25 + чистые недостачи×0.25 + SKU×0.15. "
        f"Веса: {RATING_WEIGHTS}. Выше балл — лучше. "
        "Хозтовары в расчёт не входят. Излишки, аномалии и резерв имеют вес 0, потому что в формуле v4 их нет."
    )
    work = _filters(bundle["rating"], "rating")
    _show_table(work, "rating", "рейтинг")
    if not bundle["rating"].empty:
        store = st.selectbox("Почему этот магазин на этом месте?", bundle["rating"]["магазин"].tolist())
        factors = why_store(bundle["rating"], bundle["lines"], store)
        st.write(factors.attrs.get("explanation", ""))
        _show_table(factors, "why", "факторы_рейтинга")
        sku = factors.attrs.get("sku")
        if sku is not None and not sku.empty:
            st.caption("SKU, которые формируют недостачу магазина")
            st.dataframe(sku, use_container_width=True, hide_index=True)


def page_generic(bundle, frame_key: str, title: str, note: str, chart_label: str | None = None, chart_value: str | None = None) -> None:
    st.subheader(title)
    st.caption(note)
    frame = bundle[frame_key]
    work = _filters(frame, frame_key)
    if chart_label and chart_value:
        _bar(work.head(10) if work is not None else work, chart_label, chart_value, title)
    _show_table(work, frame_key, frame_key)


def main() -> None:
    st.title("Анализ инвентаризации собственного производства")
    st.caption(
        "Контроль недостач, излишков, пересортов, перекрытий и причин "
        "инвентаризационных отклонений по магазинам сети."
    )
    st.caption(f"Версия аналитики {__version__}. Реальные файлы в репозиторий не сохраняются.")

    with st.sidebar:
        st.header("Данные")
        period = st.number_input("Период, дней", min_value=1, max_value=365, value=30)
        matching_mode = st.selectbox(
            "Режим сопоставления пар",
            ["safe_default", "extended", "full_manual_review"],
            help="safe_default ограничивает пул. extended и full_manual_review расширяют поиск, но кандидаты всё равно не уменьшают недостачу.",
        )
        max_comparisons = st.number_input("Максимум сравнений кандидатов", min_value=100, max_value=2_000_000, value=50_000, step=1000)
        max_per_side = st.number_input("Максимум позиций в одном семействе", min_value=2, max_value=20_000, value=400, step=10)
        use_demo = st.checkbox("Синтетический пример", value=False)
        inventory = st.file_uploader("Инвентаризация, xlsx", type=["xlsx"])
        capitalization = st.file_uploader("Оприходование излишков, xlsx", type=["xlsx"])
        run = st.button("Рассчитать", type="primary")

    if run:
        inv_path = None
        cap_path = None
        try:
            if use_demo:
                if not DEMO_INVENTORY.is_file():
                    st.error("Синтетический файл примера не найден в sample_data.")
                    return
                inv_path = DEMO_INVENTORY
            elif inventory is None:
                st.error("Загрузите файл инвентаризации или включите синтетический пример.")
                return
            else:
                inv_path = _save_upload(inventory)
            if capitalization is not None:
                cap_path = _save_upload(capitalization)
            with st.spinner("Считаю контур собственного производства…"):
                st.session_state["bundle"] = _load_bundle(
                    inv_path, cap_path, int(period), matching_mode, int(max_comparisons), int(max_per_side)
                )
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error(
                "Не удалось прочитать файл. Нужна исходная выгрузка инвентаризации "
                "с документами вида «Инвентаризация … от дд.мм.гггг», а не готовый аналитический отчёт."
            )
            return
        finally:
            for path in (inv_path, cap_path):
                if path is not None and path != DEMO_INVENTORY and path.exists():
                    path.unlink(missing_ok=True)

    bundle = st.session_state.get("bundle")
    tabs = st.tabs(TABS)
    if bundle is None:
        with tabs[0]:
            st.info("Загрузите выгрузку или включите синтетический пример и нажмите «Рассчитать».")
        with tabs[-1]:
            st.markdown(
                """
1. Загрузите исходный Excel инвентаризации.
2. При необходимости загрузите оприходование излишков.
3. Пары пересортов правятся в `config/related_product_pairs.csv`.
4. Классификация товара — в `config/item_scope_classification.csv`.
5. Говядина — в `config/beef_scope.csv`.
6. Кандидат на пересорт не уменьшает недостачу, пока в справочнике нет подтверждения.
7. Полный Excel скачивается на вкладке «Полные списки и экспорт».
                """
            )
        return

    with tabs[0]:
        page_home(bundle)
    with tabs[1]:
        page_generic(bundle, "shortages", "Недостачи", "Полный финансовый список, включая хозтовары.", "наименование", "недостача_сумма")
    with tabs[2]:
        page_generic(bundle, "surpluses", "Излишки", "Полный список излишков.", "наименование", "излишек_сумма")
    with tabs[3]:
        search = bundle.get("pair_search") or {}
        if search.get("limited"):
            st.warning(PAIR_POOL_WARNING)
            st.caption(search.get("completeness_text", ""))
        else:
            st.caption(search.get("completeness_text", "Кандидаты показаны отдельно и недостачу не уменьшают."))
        st.caption(
            f"Потенциальных сочетаний: {search.get('potential_rows', 0)}. "
            f"Рассмотрено: {search.get('considered', 0)}. "
            f"Исключено по несовместимости: {search.get('excluded_incompatible', 0)}. "
            f"Исключено лимитом: {search.get('excluded_by_limit', 0)}. "
            f"Предложено кандидатов: {search.get('suggested', 0)}. "
            f"Утверждённых пар: {search.get('approved', 0)}."
        )
        page_generic(bundle, "candidates", "Кандидаты на пересорт", "Эти строки не уменьшают недостачу.", "недостача_sku", "перекрытие_сум")
        st.markdown("**Подтверждённые пары справочника**")
        _show_table(bundle["applied_pairs"], "applied", "подтвержденные_пары")
        st.markdown("**Однородные перекрытия v4**")
        _show_table(bundle["legacy_overlap"], "legacy", "перекрытия_v4")
    with tabs[4]:
        page_generic(bundle, "posted_full", "Оприходованные излишки", "Группы A/B/C. Гипотеза причины не является фактом.", "Наименование", "Сумма излишка")
        st.markdown("**Структура по типу связи**")
        _show_table(bundle["posted_summary"], "posted-sum", "оприходование_резюме")
        if not bundle["posted_hypotheses"].empty and "Гипотеза причины" in bundle["posted_hypotheses"].columns:
            counts = bundle["posted_hypotheses"]["Гипотеза причины"].value_counts().rename_axis("гипотеза").reset_index(name="строк")
            _bar(counts, "гипотеза", "строк", "Гипотезы причин, число строк")
    with tabs[5]:
        st.subheader("Говядина")
        _show_table(bundle["beef_summary"], "beef-sum", "говядина_резюме")
        page_generic(bundle, "beef_shortages", "Недостачи говядины", "Только подтверждённые SKU.", "наименование", "недостача_сумма")
        st.markdown("**Строки на проверке и предварительные**")
        review = bundle["beef_full"]
        if review is not None and not review.empty and "beef_confirmed" in review.columns:
            review = review[review["beef_confirmed"] == False]  # noqa: E712
        _show_table(review, "beef-review", "говядина_проверка")
    with tabs[6]:
        page_rating(bundle)
    with tabs[7]:
        st.subheader("Резерв категорий")
        st.write(METHOD)
        _show_table(bundle["reserve"], "reserve", "резерв")
        _bar(bundle["reserve"], "Категория", "Резерв, ₽", "Резерв по категориям, ₽")
    with tabs[8]:
        hh = bundle["household"]
        sh = float(hh["недостача_сумма"].sum()) if not hh.empty else 0.0
        sur = float(hh["излишек_сумма"].sum()) if not hh.empty else 0.0
        st.metric("Недостачи хозтоваров и упаковки, ₽", f"{sh:,.2f}")
        st.metric("Излишки хозтоваров и упаковки, ₽", f"{sur:,.2f}")
        st.metric("Чистый эффект (излишки − недостачи), ₽", f"{sur - sh:,.2f}")
        page_generic(bundle, "household", "Полный список", "Эти суммы входят в общий финансовый итог и не входят в рейтинг.", "наименование", "недостача_сумма")
    with tabs[9]:
        page_generic(bundle, "prices", "Аномалии цен", "Сравнение цен между магазинами по точному наименованию.", "наименование", "разница_цены_%")
    with tabs[10]:
        st.subheader("Полные списки и экспорт")
        raw = export_workbook(bundle)
        st.download_button(
            "Скачать полный Excel",
            data=raw,
            file_name="analiz_sp_polny.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.dataframe(bundle["completeness"], use_container_width=True, hide_index=True)
        for key in ("shortages", "surpluses", "regrades", "candidates", "posted_full", "prices", "beef_full", "household", "unclassified"):
            frame = bundle[key]
            st.caption(f"{key}: {0 if frame is None else len(frame)} строк в расчёте и в выгрузке")
    with tabs[11]:
        st.subheader("Контроль качества")
        for line in bundle["quality"]:
            st.write(line)
        st.markdown("**Неклассифицированные SKU**")
        _show_table(bundle["unclassified"], "uncls", "bez_klassifikacii")
        st.caption("Эти SKU не исключены. Добавьте их в config/item_scope_classification.csv.")
    with tabs[12]:
        st.subheader("Методология")
        st.write(METHOD)
        st.write(
            "Рейтинг считается только по include_in_store_rating. "
            "Кандидат пересорта финансовый ущерб не уменьшает. "
            "Говядина в KPI блока — только строки active=1."
        )
        st.dataframe(bundle["completeness"], use_container_width=True, hide_index=True)
    with tabs[13]:
        st.subheader("Инструкция")
        st.markdown(
            """
Загрузите исходную выгрузку. Готовый файл «Анализ_…» программа отклонит.

Справочник пар: точное нормализованное имя. Пример «Семга стейк» ↔ «Форель стейк»
записан как кандидат и сам по себе недостачу не закрывает.

После согласования пары укажите тип связи из списка прямых замен и заполните approved_by.

Хозтовары остаются в денежных итогах и вынесены из рейтинга.
            """
        )


if __name__ == "__main__":
    main()
