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

## Часть 3. Загрузка данных

Для загрузки данных использовался скрипт:

```text
scripts/load_products.py
```

Скрипт генерирует каталог товаров без внешнего датасета.

Всего было сгенерировано и загружено:

```text
100 000 товаров
```

Загрузка выполнялась через HTTP `/bulk` пачками по 5000 документов.

Каждый товар содержит:

- `title` — название товара;
- `description` — текстовое описание;
- `category` — категорию;
- `brand` — бренд;
- `price` — цену;
- `rating` — рейтинг;
- `reviews_count` — количество отзывов;
- `in_stock` — наличие товара;
- `tags` — JSON-атрибуты;
- `created_at` — время создания.

В сгенерированных данных есть товары для будущих поисковых запросов:

- `wireless bluetooth headphones`;
- `noise cancelling`;
- `portable speaker`;
- `laptop`;
- `phone`;
- `gaming`.

После загрузки количество документов было проверено запросом:

```sql
SELECT COUNT(*) AS products_count FROM products;
```

Результат сохранён в файле:

```text
checks/load_products.txt
```

## Часть 4. Полнотекстовый поиск

Для проверки полнотекстового поиска были выполнены 5 типов запросов:

* базовый поиск;
* поиск точной фразы;
* proximity-поиск;
* поиск с фильтрацией по атрибутам;
* поиск по JSON-атрибуту.

SQL-запросы находятся в файле:

```text
sql/02_search_queries.sql
```

Результаты сохранены в файлах:

```text
checks/basic_search.txt
checks/phrase_search.txt
checks/proximity_search.txt
checks/filtered_search.txt
checks/json_search.txt
```

### 4.1. Базовый поиск

Запрос:

```sql
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('wireless bluetooth headphones')
ORDER BY w DESC
LIMIT 10;
```

Пример результата:

| id | title                                 |    w |
| -: | ------------------------------------- | ---: |
| 10 | Sony Wireless Bluetooth Headphones 10 | 6537 |
| 20 | Sony Wireless Bluetooth Headphones 20 | 6537 |
| 30 | Sony Wireless Bluetooth Headphones 30 | 6537 |
| 40 | Sony Wireless Bluetooth Headphones 40 | 6537 |
| 50 | Sony Wireless Bluetooth Headphones 50 | 6537 |

Время выполнения:

```text
0.0704 sec
```

Запрос ищет документы, где встречаются слова `wireless`, `bluetooth`, `headphones`.
Поле `WEIGHT()` показывает релевантность найденного документа.

### 4.2. Поиск точной фразы

Запрос:

```sql
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"noise cancelling"')
ORDER BY w DESC
LIMIT 10;
```

Пример результата:

| id | title                                  |    w |
| -: | -------------------------------------- | ---: |
|  1 | Samsung Noise Cancelling Headphones 1  | 4537 |
| 11 | Samsung Noise Cancelling Headphones 11 | 4537 |
| 21 | Samsung Noise Cancelling Headphones 21 | 4537 |
| 31 | Samsung Noise Cancelling Headphones 31 | 4537 |
| 41 | Samsung Noise Cancelling Headphones 41 | 4537 |

Время выполнения:

```text
0.0275 sec
```

Кавычки в `MATCH('"noise cancelling"')` означают, что ManticoreSearch ищет точную фразу, а не просто отдельные слова.

### 4.3. Proximity-поиск

Запрос:

```sql
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"portable speaker"~3')
ORDER BY w DESC
LIMIT 10;
```

Пример результата:

| id | title                     |    w |
| -: | ------------------------- | ---: |
|  2 | Apple Portable Speaker 2  | 3559 |
| 12 | Apple Portable Speaker 12 | 3559 |
| 22 | Apple Portable Speaker 22 | 3559 |
| 32 | Apple Portable Speaker 32 | 3559 |
| 42 | Apple Portable Speaker 42 | 3559 |

Время выполнения:

```text
0.0100 sec
```

Оператор `~3` означает, что слова должны находиться рядом друг с другом в пределах заданного расстояния.
Такой поиск полезен, когда важен смысл фразы, но слова могут находиться не строго подряд.

### 4.4. Поиск с фильтрацией по атрибутам

Запрос:

```sql
SELECT id, title, price, rating
FROM products
WHERE MATCH('laptop')
  AND price BETWEEN 30000 AND 80000
  AND rating >= 4.0
ORDER BY rating DESC
LIMIT 10;
```

Пример результата:

|  id | title                  | price | rating |
| --: | ---------------------- | ----: | -----: |
|  63 | Lenovo Laptop Pro 63   | 55053 |      5 |
|  79 | Dell Gaming Laptop 79  | 75069 |      5 |
| 143 | Lenovo Laptop Pro 143  | 55133 |      5 |
| 159 | Dell Gaming Laptop 159 | 75149 |      5 |
| 223 | Lenovo Laptop Pro 223  | 55213 |      5 |

Время выполнения:

```text
0.0130 sec
```

В этом запросе полнотекстовый поиск совмещён с фильтрами по атрибутам:

* цена от `30000` до `80000`;
* рейтинг не ниже `4.0`.

Такой сценарий типичен для интернет-магазина: пользователь ищет товар текстом, а затем ограничивает выдачу фильтрами.

### 4.5. Поиск по JSON-атрибуту

Запрос:

```sql
SELECT id, title, tags
FROM products
WHERE MATCH('phone')
  AND tags.color = 'black'
LIMIT 10;
```

Пример результата:

| id | title               | tags.color |
| -: | ------------------- | ---------- |
|  4 | Asus Smart Phone 4  | black      |
| 14 | Asus Smart Phone 14 | black      |
| 24 | Asus Smart Phone 24 | black      |
| 34 | Asus Smart Phone 34 | black      |
| 44 | Asus Smart Phone 44 | black      |

Время выполнения:

```text
0.0215 sec
```

Поле `tags` имеет тип JSON.
В запросе используется условие:

```sql
tags.color = 'black'
```

Это показывает NoSQL-элемент ManticoreSearch: можно хранить дополнительные свойства товара в JSON и фильтровать результаты поиска по вложенным атрибутам.

### Вывод

ManticoreSearch позволяет совмещать полнотекстовый поиск и фильтрацию по структурированным атрибутам.

В рамках проверки были использованы:

* релевантность через `WEIGHT()`;
* поиск точной фразы;
* proximity-поиск;
* числовые фильтры по цене и рейтингу;
* фильтрация по JSON-полю.

Такой подход хорошо подходит для каталога товаров, где пользователь ищет по тексту, а затем уточняет выдачу фильтрами.
