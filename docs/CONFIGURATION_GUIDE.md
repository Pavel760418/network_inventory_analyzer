# Настройка справочников

Файлы лежат в `config/`. Кодировка UTF-8. Разделитель — запятая. Текст с запятой берите в кавычки.

## Пары

1. Добавьте строку с двумя разными наименованиями.
2. Пока связь не согласована, ставьте `relationship_type=requires_manual_review` и пустой `approved_by`.
3. После согласования укажите один из типов: `exact_substitution`, `same_raw_material`, `same_cut_or_format`, `same_product_family`, `production_ingredient_substitution`, и заполните `approved_by`.
4. Самопара с одинаковыми именами не используется.

## Классификация

Точечная строка в `item_scope_classification.csv` важнее `scope_rules.csv`.
Чтобы вывести хозтовар из рейтинга, поставьте флаги `include_in_store_rating`, `include_in_shortage_top`, `include_in_regrading` в 0.
Чтобы вернуть позицию в рейтинг, поставьте 1.
Пустая классификация не удаляет строку.

## Говядина

Подтверждённая сумма меняется только строкой с `active=1`.
Сомнительное имя оставляйте с `active=0`.
