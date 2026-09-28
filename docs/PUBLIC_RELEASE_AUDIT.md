# Аудит публичной поставки

Проверено до публикации.

Включено: исходный код, тесты, документация, `config/*.csv`, синтетический `sample_data/demo_inventory_synthetic.xlsx`, фикстура `data/fixtures/master_hierarchy_sample.json`, `.streamlit/config.toml`, `requirements.txt`.

Исключено: `.venv`, `.env`, `secrets.toml`, каталог реальных выгрузок, `data/master_hierarchy.json`, `data/master_hierarchy.csv`, отчёты `output/`, `exports/`, `reports/`.

Поиск по проекту вне `.venv` не показал токенов и паролей в добавляемых файлах.
Локальные абсолютные пути пользователя в публикуемых документах не записаны.
Реальных инвентаризаций в синтетическом примере нет: два вымышленных магазина и учебные суммы.

Идентификатор коммита поставки — `git rev-parse HEAD` после публикации ветки.
Пока владелец аккаунта не нажмёт Deploy в Streamlit Community Cloud, публичный URL приложения отсутствует.
