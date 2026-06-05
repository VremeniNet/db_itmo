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

## Часть 2. Создание RT-индекса

Для каталога товаров был создан real-time индекс `products`.

DDL находится в файле:

```text
sql/01_create_index.sql
```

Индекс создаётся командой:

```sql
CREATE TABLE products (
    title         text,
    description   text,
    category      string,
    brand         string,
    price         float,
    rating        float,
    reviews_count integer,
    in_stock      bool,
    tags          json,
    created_at    timestamp
) morphology='stem_enru' min_word_len='2' html_strip='1';
```

Поля `title` и `description` имеют тип `text`.
Это полнотекстовые поля, по которым можно выполнять поиск через `MATCH()`.

Остальные поля используются как атрибуты:

* `category` — категория товара;
* `brand` — бренд;
* `price` — цена;
* `rating` — рейтинг;
* `reviews_count` — количество отзывов;
* `in_stock` — наличие товара;
* `tags` — JSON-атрибуты;
* `created_at` — дата создания записи.

Параметр:

```sql
morphology='stem_enru'
```

включает стемминг для английского и русского языка.
Это значит, что ManticoreSearch может приводить слова к основе. Например, разные формы слова будут лучше находиться одним запросом.

Параметр:

```sql
min_word_len='2'
```

задаёт минимальную длину слова для индексации.
Слишком короткие слова часто не несут полезного смысла и могут только увеличивать размер индекса.

Параметр:

```sql
html_strip='1'
```

включает удаление HTML-тегов из текстовых полей.
Это полезно для описаний товаров, потому что в реальных каталогах описание может содержать HTML-разметку.

RT-индекс отличается от plain-индекса тем, что в него можно добавлять, обновлять и удалять документы без полной переиндексации.
Это удобно для интернет-магазина, где товары, цены, рейтинги и наличие могут меняться часто.

После выполнения SQL-файла индекс `products` был создан и проверен через `SHOW TABLES` и `DESC products`.
