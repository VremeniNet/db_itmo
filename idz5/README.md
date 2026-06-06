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

## Часть 5. Фасетный поиск и агрегации

Для проверки фасетного поиска и агрегаций использовались запросы из файла:

```text
sql/03_facets.sql
```

Результаты сохранены в файле:

```text
checks/facets.txt
```

### Агрегация по категориям

Запрос:

```sql
SELECT
    category,
    COUNT(*) AS cnt,
    AVG(price) AS avg_price
FROM products
WHERE MATCH('gaming')
GROUP BY category
ORDER BY cnt DESC;
```

Результат:

| category | cnt | avg_price |
|---|---:|---:|
| Gaming | 20000 | 6240.5 |
| Computers | 20000 | 66241.0 |

Время выполнения:

```text
0.7426 sec
```

Запрос показывает, в каких категориях встречаются товары по запросу `gaming`, сколько таких товаров найдено и какая у них средняя цена.

### FACET по категории и бренду

Запрос:

```sql
SELECT id, title, price
FROM products
WHERE MATCH('gaming')
LIMIT 10
FACET category ORDER BY COUNT(*) DESC
FACET brand ORDER BY COUNT(*) DESC;
```

В первой части результата ManticoreSearch вернул найденные товары:

| id | title | price |
|---:|---|---:|
| 5 | Logitech Gaming Mouse 5 | 2995 |
| 6 | Xiaomi Gaming Keyboard 6 | 6996 |
| 9 | Dell Gaming Laptop 9 | 74999 |
| 15 | Logitech Gaming Mouse 15 | 3005 |
| 16 | Xiaomi Gaming Keyboard 16 | 7006 |

Фасет по категориям:

| category | count |
|---|---:|
| Gaming | 20000 |
| Computers | 20000 |

Фасет по брендам:

| brand | count |
|---|---:|
| Lenovo | 10000 |
| Logitech | 10000 |
| Xiaomi | 10000 |
| Dell | 10000 |

Время выполнения:

```text
0.3072 sec
```

Фасетный поиск полезен для e-commerce, потому что он позволяет строить фильтры каталога поверх результатов поиска.

Например, пользователь ищет `gaming`, а система сразу показывает доступные фильтры:

- категории;
- бренды;
- диапазоны цен;
- наличие;
- рейтинг.

Главное отличие фасетов от обычного поиска в том, что пользователь получает не только список товаров, но и структуру для уточнения выдачи. Это делает поиск по каталогу удобнее: можно быстро сузить результат до нужной категории или бренда.

## Часть 6. Сравнение с PostgreSQL

Для сравнения с ManticoreSearch был выполнен полнотекстовый поиск в PostgreSQL.

SQL-запросы находятся в файле:

```text
sql/05_pg_comparison.sql
```

Результаты сохранены в файле:

```text
checks/pg_vs_manticore.txt
```

В PostgreSQL была создана таблица `pg_products` на 100 000 товаров.
Для полнотекстового поиска был добавлен столбец `tsv`:

```sql
ALTER TABLE pg_products
ADD COLUMN tsv tsvector
GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))
) STORED;
```

Для ускорения поиска был создан GIN-индекс:

```sql
CREATE INDEX idx_pg_products_tsv ON pg_products USING GIN(tsv);
```

Поиск выполнялся запросом:

```sql
SELECT
    title,
    ts_rank(tsv, q) AS rank
FROM pg_products,
     to_tsquery('english', 'wireless & bluetooth & headphones') q
WHERE tsv @@ q
ORDER BY rank DESC
LIMIT 10;
```

PostgreSQL нашёл товары `Sony Wireless Bluetooth Headphones`.

Время выполнения PostgreSQL-запроса по `EXPLAIN ANALYZE`:

```text
Execution Time: 16.950 ms
```

Для ManticoreSearch использовался запрос:

```sql
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('wireless bluetooth headphones')
ORDER BY w DESC
LIMIT 10;
```

Время выполнения ManticoreSearch-запроса:

```text
0.0704 sec
```

### Сравнение

| Характеристика        | ManticoreSearch                                    | PostgreSQL `tsvector + GIN`                                 |
| --------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| Количество документов | 100000                                             | 100000                                                      |
| Время поиска          | 0.0704 sec                                         | 16.950 ms                                                   |
| Тип поиска            | `MATCH()`                                          | `tsvector` + `to_tsquery()`                                 |
| Ранжирование          | BM25 / `WEIGHT()`                                  | `ts_rank()`                                                 |
| Морфология            | `stem_enru` в настройках индекса                   | конфигурация `english`                                      |
| Фасетный поиск        | Есть отдельный синтаксис `FACET`                   | Нужно писать вручную через `GROUP BY`                       |
| JSON-атрибуты         | Есть тип `json`, можно фильтровать по `tags.color` | Есть `jsonb` и JSON-операторы                               |
| Транзакции            | Нет классических SQL-транзакций                    | Есть                                                        |
| Основной сценарий     | Быстрый поиск по каталогу, релевантность, фасеты   | Хранение данных, транзакции, поиск как часть реляционной БД |

### Вывод

В этом конкретном тесте PostgreSQL выполнил один поисковый запрос быстрее. Но сравнение не сводится только к одному времени выполнения.

PostgreSQL хорошо подходит, если полнотекстовый поиск является дополнительной функцией внутри реляционной базы данных. Он поддерживает транзакции, ограничения, связи между таблицами и обычные SQL-операции.

ManticoreSearch лучше подходит как отдельный поисковый движок для каталога товаров. Он даёт удобный полнотекстовый поиск, релевантность через `WEIGHT()`, фасеты, JSON-атрибуты и real-time индекс, в который можно быстро добавлять и обновлять документы.

Для интернет-магазина PostgreSQL можно использовать как основную базу данных, а ManticoreSearch — как отдельный поисковый слой для каталога.

## Часть 7. Обновление и удаление документов

Для проверки NoSQL-аспекта ManticoreSearch были выполнены операции:

- `UPDATE`;
- `DELETE`;
- `REPLACE`.

SQL-запросы находятся в файле:

```text
sql/04_update_delete.sql
```

Результаты сохранены в файле:

```text
checks/update_delete.txt
```

### UPDATE

Сначала был выбран товар с `id = 4`:

| id | title | price | rating |
|---:|---|---:|---:|
| 4 | Asus Smart Phone 4 | 39994 | 3.9 |

Затем была выполнена команда:

```sql
UPDATE products
SET price = 29999, rating = 4.9
WHERE id = 4;
```

После обновления товар получил новые значения:

| id | title | price | rating |
|---:|---|---:|---:|
| 4 | Asus Smart Phone 4 | 29999 | 4.9 |

ManticoreSearch обновил атрибуты документа.  
При этом в ответе появилось предупреждение про вторичный индекс:

```text
secondary index disabled for attribute(s) 'price,rating' after attribute update; run ALTER TABLE REBUILD SECONDARY
```

Это означает, что после массовых обновлений атрибутов может потребоваться перестроить вторичные индексы.

### DELETE

Для демонстрации удаления был добавлен временный документ:

```sql
REPLACE INTO products (...)
VALUES (
    200001,
    'Delete Demo Unique Headphones',
    ...
);
```

До удаления поиск находил документ:

| id | title |
|---:|---|
| 200001 | Delete Demo Unique Headphones |

После этого была выполнена команда:

```sql
DELETE FROM products
WHERE id = 200001;
```

После удаления поиск по запросу:

```sql
SELECT id, title
FROM products
WHERE MATCH('delete demo unique')
LIMIT 10;
```

вернул пустой результат:

```text
total: 0
```

Это подтверждает, что документ был удалён из индекса.

### REPLACE

Для проверки `REPLACE` сначала был добавлен документ:

| id | title | price | rating | tags |
|---:|---|---:|---:|---|
| 200002 | Replace Demo Old Product | 1000 | 3.0 | `{"color":"white","version":"old"}` |

Затем была выполнена команда `REPLACE INTO` с тем же `id = 200002`, но с новым содержимым:

```sql
REPLACE INTO products (...)
VALUES (
    200002,
    'Replace Demo New Product',
    ...
);
```

После `REPLACE` документ изменился:

| id | title | price | rating | tags |
|---:|---|---:|---:|---|
| 200002 | Replace Demo New Product | 2500 | 4.8 | `{"color":"blue","version":"new"}` |

Поиск старого содержимого:

```sql
SELECT id, title
FROM products
WHERE MATCH('replace demo old')
LIMIT 10;
```

вернул пустой результат.

Поиск нового содержимого:

```sql
SELECT id, title
FROM products
WHERE MATCH('replace demo new')
LIMIT 10;
```

нашёл документ:

| id | title |
|---:|---|
| 200002 | Replace Demo New Product |

### Отличие от PostgreSQL

В PostgreSQL `UPDATE`, `DELETE` и `INSERT` обычно выполняются внутри транзакционной модели.  
Можно использовать `BEGIN`, `COMMIT`, `ROLLBACK`, ограничения целостности и связи между таблицами.

В ManticoreSearch эти операции работают иначе.  
ManticoreSearch ориентирован не на транзакционную обработку, а на быстрый поиск и обновление документов в индексе.

Основные отличия:

- нет классических SQL-транзакций как в PostgreSQL;
- документ можно быстро обновить, удалить или заменить по `id`;
- `REPLACE` заменяет документ целиком;
- структура больше похожа на работу с поисковым индексом, а не с реляционной таблицей;
- в кластере возможна eventual consistency, то есть реплики могут синхронизироваться не строго мгновенно.

Вывод: ManticoreSearch удобно использовать как поисковый слой для каталога товаров, где нужно быстро искать, фильтровать и обновлять документы. PostgreSQL лучше подходит для основной транзакционной базы данных.