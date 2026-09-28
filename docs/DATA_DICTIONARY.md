# Словарь данных

## Строка инвентаризации

| Поле | Смысл |
|------|--------|
| магазин | Подразделение выгрузки |
| документ | Строка «Инвентаризация …» |
| наименование | Номенклатура |
| недостача_сумма | Сумма недостачи, ₽ |
| излишек_сумма | Сумма излишка, ₽ |
| category_group | Группа для однородного перекрытия v4 |
| scope | Контур из справочника |
| include_in_store_rating | 1 — строка входит в рейтинг |
| beef_status | пусто, подтверждено, на проверке, предварительно классифицировано |

## Пара пересорта

`pair_id`, имена и id двух сторон, `relationship_type`, `match_level`, `priority`, `active`, даты, `source`, `comment`, `approved_by`, `approved_at`.

## Scope

`own_production_ingredient`, `own_production_raw_material`, `finished_goods`, `household_supply`, `packaging`, `container`, `consumable`, `equipment`, `other_non_core`, `unclassified`.
