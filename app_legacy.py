# -*- coding: utf-8 -*-
"""Streamlit UI — Release 4.

1) Inventory Excel
2) Capitalization (оприходование излишков) Excel
Hierarchy is embedded; no hierarchy upload.
Shows anomalies + cross-store price check after analysis.
"""
from __future__ import annotations

import datetime
import sys
import tempfile
import traceback
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import PERIOD_DAYS, load_settings
from src.anomalies import (
    TYPE_1,
    TYPE_2,
    TYPE_3,
    anomalies_summary,
    detect_book_sum_anomalies,
)
from src.capitalization import (
    capitalization_summary,
    match_capitalization_to_inventory,
    parse_capitalization_excel,
)
from src.catalog import enrich_dataframe, load_catalog, unmatched_summary
from src.master_hierarchy import get_master_hierarchy
from src.metrics import (
    calc_network_summary,
    calc_sku_cross,
    calc_store_metrics,
    generate_conclusions,
)
from src.models import Config
from src.overlap import build_analytical_cross_store, build_operational_overlaps
from src.parser import filter_by_period, parse_network_excel
from src.pipeline import run_analysis
from src.price_compare import (
    STATUS_CHECK,
    STATUS_NOTICE,
    compare_prices_across_stores,
    price_compare_summary,
)
from src import __version__

st.set_page_config(
    page_title="Анализатор инвентаризаций сети — R4",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _save_upload(uploaded, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded.getvalue())
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def render_sidebar():
    settings = load_settings()
    st.sidebar.header("Параметры анализа")
    st.sidebar.caption(f"Release {__version__}")
    try:
        master = get_master_hierarchy()
        st.sidebar.success(
            f"Эталон иерархии\n\n{master.source_file}\n"
            f"{len(master.items):,} SKU · глубина {master.max_depth}"
        )
    except FileNotFoundError as exc:
        st.sidebar.error(str(exc))

    period_days = st.sidebar.number_input(
        "Период, дней",
        min_value=1,
        max_value=365,
        value=int(settings.period_days or PERIOD_DAYS),
    )
    enable_cross = st.sidebar.checkbox(
        "Аналитика между магазинами",
        value=bool(settings.enable_cross_store),
    )
    use_custom_end = st.sidebar.checkbox("Задать конечную дату вручную", value=False)
    end_date = None
    if use_custom_end:
        end_date = st.sidebar.date_input("Конечная дата", value=datetime.date.today())
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Нужны 2 файла: инвентаризация + оприходование излишков при закрытии смены. "
        "Иерархия уже встроена. Release 4: аномалии книжных сумм и проверка цен."
    )
    return period_days, enable_cross, end_date


def main() -> None:
    st.title("Анализатор инвентаризаций сети — Release 4")
    st.markdown(
        "Эталонная иерархия встроена. После основного файла загрузите "
        "**оприходование излишков** (закрытие смены). "
        "Дополнительно фиксируются **аномалии книжных сумм** и "
        "**проверка цен между магазинами** (точное наименование)."
    )

    with st.expander("Как пользоваться (R4)", expanded=False):
        st.markdown(
            """
1. Загрузите **исходный Excel инвентаризаций**.
2. Загрузите **Excel оприходования излишков** (закрытие кассовой смены).
3. Запустите анализ.
4. Скачайте отчёт: Сводка / Выводы / Рейтинг + листы
   **«Аномалии»**, **«Проверка цен»**, **«Оприходование излишков»**.
            """
        )

    period_days, enable_cross, end_date = render_sidebar()

    st.subheader("1. Инвентаризация")
    uploaded = st.file_uploader(
        "Исходный Excel инвентаризаций",
        type=["xlsx"],
        accept_multiple_files=False,
        key="inv_file",
    )

    st.subheader("2. Оприходование излишков")
    st.info(
        "Файл нужен для сверки оприходования при закрытии смены с недостачами/излишками "
        "инвентаризации. Данные разных складов не смешиваются."
    )
    cap_uploaded = st.file_uploader(
        "Excel оприходования (Закрытие смены количество / сумма)",
        type=["xlsx"],
        accept_multiple_files=False,
        key="cap_file",
    )

    ready = uploaded is not None and cap_uploaded is not None
    run = st.button("Запустить анализ Release 4", type="primary", disabled=not ready)
    if not ready:
        st.warning("Загрузите оба файла, чтобы запустить анализ.")
        return
    if not run:
        return

    if getattr(uploaded, "size", 1) == 0 or getattr(cap_uploaded, "size", 1) == 0:
        st.error("Один из файлов пустой.")
        return

    input_path = _save_upload(uploaded, ".xlsx")
    cap_path = _save_upload(cap_uploaded, ".xlsx")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(tempfile.gettempdir()) / f"Анализ_сеть_{Path(uploaded.name).stem}_{ts}.xlsx"

    cfg = Config(
        input_path=str(input_path),
        output_path=str(out_path),
        period_days=int(period_days),
        end_date=end_date if isinstance(end_date, datetime.date) else None,
        catalog_path=None,
        enable_cross_store=bool(enable_cross),
        capitalization_path=str(cap_path),
    )

    progress = st.progress(0, text="Чтение инвентаризации…")
    try:
        df, meta = parse_network_excel(cfg.input_path)
        progress.progress(12, text="Фильтр периода…")
        end = cfg.end_date or meta.date_max
        df = filter_by_period(df, cfg.period_days, end)
        if df.empty:
            st.error("После фильтрации по периоду не осталось данных.")
            return

        progress.progress(25, text="Эталонная иерархия…")
        df = enrich_dataframe(df, load_catalog(None))
        um = unmatched_summary(df)

        progress.progress(40, text="Перекрытия и метрики…")
        overlap_op = build_operational_overlaps(df)
        if cfg.enable_cross_store:
            _ = build_analytical_cross_store(df)
        store_metrics = calc_store_metrics(df, overlap_op)
        sku_cross = calc_sku_cross(df)
        chronic = sku_cross[sku_cross["chronic"]]
        summary = calc_network_summary(df, overlap_op)

        progress.progress(55, text="Аномалии и проверка цен…")
        anom_df = detect_book_sum_anomalies(df)
        anom_sum = anomalies_summary(anom_df, total_rows=len(df))
        price_df = compare_prices_across_stores(df)
        price_sum = price_compare_summary(price_df, df)

        progress.progress(70, text="Оприходование излишков…")
        cap_raw = parse_capitalization_excel(cfg.capitalization_path)
        cap_matched = match_capitalization_to_inventory(cap_raw, df)
        cap_sum = capitalization_summary(cap_matched)
        conclusions = generate_conclusions(
            summary, store_metrics, chronic,
            cap_summary=cap_sum,
            anom_summary=anom_sum,
            price_summary=price_sum,
        )

        progress.progress(85, text="Формирование Excel…")
        result_path = run_analysis(cfg)
        progress.progress(100, text="Готово")

        st.success("Release 4: анализ завершён.")

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Магазинов", summary["stores"])
        c2.metric("Недостачи", f"{summary['shortage']:,.0f}")
        c3.metric("Аномалии", int(anom_sum["total"]))
        c4.metric("Критич. аном.", int(anom_sum["critical"]))
        c5.metric("Ценовых пар", int(price_sum["pairs"]))
        c6.metric("Оприход. сумма", f"{cap_sum['cap_sum']:,.0f}")

        st.markdown(
            f"**Краткий вывод:** аномалий книжных сумм — **{int(anom_sum['total'])}** "
            f"(критических тип 2: {int(anom_sum['critical'])}); "
            f"ценовых пересечений — **{int(price_sum['names'])}** позиций "
            f"({int(price_sum['check'])} требуют проверки цен сумма÷кол); "
            f"оприходование сопоставлено "
            f"**{int(cap_sum['matched'] + cap_sum['matched_shortage'])}** строк."
        )

        # --- Anomalies block ---
        st.subheader("Аномалии книжных сумм")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric(TYPE_1, int(anom_sum["type1"]))
        a2.metric(TYPE_2 + " (крит.)", int(anom_sum["type2"]))
        a3.metric(TYPE_3, int(anom_sum["type3"]))
        a4.metric("Доля строк", f"{anom_sum['share_pct']:.1f}%")
        if not anom_df.empty:
            stores = sorted(anom_df["магазин"].dropna().astype(str).unique())
            types = sorted(anom_df["тип_аномалии"].dropna().astype(str).unique())
            f1, f2 = st.columns(2)
            store_f = f1.multiselect("Фильтр: магазин", stores, default=[])
            type_f = f2.multiselect("Фильтр: тип аномалии", types, default=[])
            view = anom_df
            if store_f:
                view = view[view["магазин"].isin(store_f)]
            if type_f:
                view = view[view["тип_аномалии"].isin(type_f)]
            show_cols = [
                c for c in [
                    "наименование", "магазин", "тип_аномалии",
                    "книжная_нормативная_сумма", "книжная_фактическая_сумма",
                    "критичность", "комментарий",
                ] if c in view.columns
            ]
            st.dataframe(view[show_cols].head(200), use_container_width=True)
        else:
            st.info("Аномалий книжных сумм не найдено.")

        # --- Price check block ---
        st.subheader("Проверка цен между магазинами")
        st.caption(
            "Сравниваются **цены** (не суммы): "
            "цена норм. = сумма книжная нормативная ÷ кол. книжное; "
            "цена факт. = сумма фактическая ÷ кол. фактическое."
        )
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Пересеч. позиций", int(price_sum["names"]))
        p2.metric("Пар сравнений", int(price_sum["pairs"]))
        p3.metric("Требуют проверки", int(price_sum["check"]))
        p4.metric("Ср. расхожд. %", f"{price_sum['avg_gap_pct']:.1f}")
        if not price_df.empty:
            statuses = sorted(price_df["статус_проверки"].dropna().astype(str).unique())
            st_f = st.multiselect(
                "Фильтр: статус проверки",
                statuses,
                default=[s for s in statuses if s in (STATUS_CHECK, STATUS_NOTICE)],
            )
            pview = price_df if not st_f else price_df[price_df["статус_проверки"].isin(st_f)]
            show_p = [
                c for c in [
                    "наименование", "магазин_1", "магазин_2",
                    "кол_норм_1", "сумма_норм_1", "цена_книжная_нормативная_1",
                    "кол_норм_2", "сумма_норм_2", "цена_книжная_нормативная_2",
                    "кол_факт_1", "сумма_факт_1", "цена_книжная_фактическая_1",
                    "кол_факт_2", "сумма_факт_2", "цена_книжная_фактическая_2",
                    "процент_расхождения", "статус_проверки", "комментарий",
                ] if c in pview.columns
            ]
            st.dataframe(pview[show_p].head(200), use_container_width=True)
        else:
            st.info("Пересекающихся позиций для сравнения цен нет.")

        # --- Capitalization block ---
        st.subheader("Оприходование излишков")
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Сопоставлено", int(cap_sum["matched"] + cap_sum["matched_shortage"]))
        o2.metric("↔ Недостача", int(cap_sum["matched_shortage"]))
        o3.metric(
            "Не сопоставлено",
            int(cap_sum["unmatched_name"] + cap_sum["unmatched_store"] + cap_sum["uncertain_store"]),
        )
        o4.metric("Складов", int(cap_sum["warehouses"]))
        if not cap_matched.empty:
            by_wh = (
                cap_matched.groupby("склад", dropna=False)
                .agg(строк=("наименование", "count"), сумма=("оп_сумма", "sum"))
                .reset_index()
                .sort_values("сумма", ascending=False)
            )
            st.dataframe(by_wh, use_container_width=True)
            with st.expander("Детализация оприходования (топ-100)"):
                st.dataframe(cap_matched.head(100), use_container_width=True)

        if int((~df["hierarchy_matched"]).sum()):
            st.warning(
                f"Вне эталонной иерархии: {int((~df['hierarchy_matched']).sum()):,} строк "
                f"({len(um):,} уник. наименований)."
            )

        st.subheader("Выводы")
        for title, text in conclusions:
            st.markdown(f"**{title}.** {text}")

        st.subheader("Рейтинг магазинов")
        st.dataframe(store_metrics, use_container_width=True)

        data = Path(result_path).read_bytes()
        st.download_button(
            label="Скачать Excel-отчёт (Release 4)",
            data=data,
            file_name=Path(result_path).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.error(f"Ошибка анализа: {exc}")
        st.code(traceback.format_exc())
    finally:
        for p in (input_path, cap_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()
