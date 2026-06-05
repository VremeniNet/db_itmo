# ИДЗ-5. ManticoreSearch: полнотекстовый поиск и NoSQL-подход

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных
**СУБД:** ManticoreSearch

## Цель работы

Развернуть ManticoreSearch, создать real-time индекс для каталога товаров, загрузить тестовые данные, выполнить полнотекстовый поиск, фасетный поиск и сравнить подход поискового движка с PostgreSQL.

## Структура

```text
idz5/
├── README.md
├── docker-compose.yml
├── config/
│   └── manticore.conf
├── sql/
│   ├── 01_create_index.sql
│   ├── 02_search_queries.sql
│   ├── 03_facets.sql
│   ├── 04_update_delete.sql
│   └── 05_pg_comparison.sql
├── scripts/
│   └── load_products.py
└── checks/
    ├── connectivity.txt
    ├── basic_search.txt
    ├── phrase_search.txt
    ├── proximity_search.txt
    ├── filtered_search.txt
    ├── json_search.txt
    ├── facets.txt
    ├── update_delete.txt
    └── pg_vs_manticore.txt
```
## Часть 1. Установка и проверка подключения

ManticoreSearch был запущен в Docker-контейнере `idz5-manticore`.

Для запуска используется файл:

```text
docker-compose.yml
```

Контейнер публикует два порта:

- `9306` — MySQL-совместимый протокол;
- `9308` — HTTP API.

Проверка MySQL-протокола выполнялась командой:

```powershell
docker run --rm --network idz5-net mysql:8.0 mysql -hmanticore -P9306 --protocol=tcp -e "SHOW TABLES;"
```

Проверка HTTP API выполнялась командой:

```powershell
curl.exe -s http://localhost:9308/sql -d "query=SHOW TABLES"
```

Результаты проверки сохранены в файле:

```text
checks/connectivity.txt
```
