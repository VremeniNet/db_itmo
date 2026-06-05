# ИДЗ-4. Шардирование в ClickHouse

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных
**СУБД:** ClickHouse

## Цель работы

Развернуть шардированный кластер ClickHouse, настроить локальные и распределённые таблицы, проверить распределение данных по шардам и выполнить запросы через `Distributed`-движок.

## Структура

```text
idz4/
├── README.md
├── docker-compose.yml
├── config/
│   ├── keeper/
│   │   ├── keeper1.xml
│   │   ├── keeper2.xml
│   │   └── keeper3.xml
│   └── clickhouse/
│       ├── cluster.xml
│       ├── s1r1_macros.xml
│       ├── s1r2_macros.xml
│       ├── s2r1_macros.xml
│       └── s2r2_macros.xml
├── sql/
│   ├── 01_create_local.sql
│   ├── 02_create_distributed.sql
│   ├── 03_user_dict.sql
│   └── 04_queries.sql
├── scripts/
│   └── generate_clickstream.py
└── checks/
    ├── cluster_info.txt
    ├── data_distribution.txt
    ├── distributed_queries.txt
    └── reshard_demo.txt
```

## Часть 1. Кластер 2x2

Кластер развёрнут через Docker Compose.

Используются 4 узла ClickHouse:

- `ch-s1-r1` — шард 1, реплика 1;
- `ch-s1-r2` — шард 1, реплика 2;
- `ch-s2-r1` — шард 2, реплика 1;
- `ch-s2-r2` — шард 2, реплика 2.

Также используются 3 узла ClickHouse Keeper:

- `keeper1`;
- `keeper2`;
- `keeper3`.

Keeper нужен для координации репликации таблиц `ReplicatedMergeTree`.

В конфигурации `remote_servers` описан кластер `cluster_2x2`:

- 2 шарда;
- по 2 реплики в каждом шарде.

Для каждого ClickHouse-узла заданы макросы:

- `{shard}`;
- `{replica}`;
- `{cluster}`.

Макросы используются при создании реплицированных таблиц, чтобы каждая реплика имела своё имя, а таблицы одного шарда использовали общий путь в ClickHouse Keeper.

Проверка кластера выполнялась запросом:

```sql
SELECT
    cluster,
    shard_num,
    replica_num,
    host_name,
    port
FROM system.clusters
WHERE cluster = 'cluster_2x2'
ORDER BY
    shard_num,
    replica_num;
```

Результат сохранён в файле:

```text
checks/cluster_info.txt
```

Результат проверки:

| cluster | shard_num | replica_num | host_name | port |
|---|---:|---:|---|---:|
| cluster_2x2 | 1 | 1 | ch-s1-r1 | 9000 |
| cluster_2x2 | 1 | 2 | ch-s1-r2 | 9000 |
| cluster_2x2 | 2 | 1 | ch-s2-r1 | 9000 |
| cluster_2x2 | 2 | 2 | ch-s2-r2 | 9000 |

## Часть 2. Локальные и распределённые таблицы

Для хранения событий пользовательской аналитики создана локальная таблица `events_local`.

DDL находится в файле:

```text
sql/01_create_local.sql
```

Таблица `events_local` создана на движке `ReplicatedMergeTree`:

```sql
CREATE TABLE idz4.events_local ON CLUSTER cluster_2x2 (
    event_date  Date,
    event_time  DateTime,
    user_id     UInt64,
    session_id  String,
    event_type  LowCardinality(String),
    page_url    String,
    duration_ms UInt32
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/events_local',
    '{replica}'
)
PARTITION BY toYYYYMM(event_date)
ORDER BY (user_id, event_time);
```

Локальная таблица физически хранит данные на конкретных узлах ClickHouse.

Так как таблица создана на `ReplicatedMergeTree`, внутри каждого шарда данные реплицируются между двумя репликами:

- шард 1: `ch-s1-r1`, `ch-s1-r2`;
- шард 2: `ch-s2-r1`, `ch-s2-r2`.

Для работы со всеми шардами создана распределённая таблица `events_distributed`.

DDL находится в файле:

```text
sql/02_create_distributed.sql
```

```sql
CREATE TABLE idz4.events_distributed ON CLUSTER cluster_2x2
AS idz4.events_local
ENGINE = Distributed(
    'cluster_2x2',
    'idz4',
    'events_local',
    xxHash64(user_id)
);
```

Таблица `events_distributed` сама данные не хранит. Она маршрутизирует запросы и вставки в локальные таблицы `events_local` на нужных шардах.

В качестве ключа шардирования выбран:

```sql
xxHash64(user_id)
```

Ключ `user_id` выбран потому, что события одного пользователя логически связаны между собой. Если все события одного пользователя попадают на один шард, то запросы по пользователю и агрегации по `user_id` выполняются эффективнее.

`event_date` не выбран ключом шардирования, потому что тогда данные могли бы распределяться неравномерно: например, популярные дни получили бы слишком много строк.

`rand()` тоже не подходит, потому что он распределял бы строки случайно. В таком случае события одного пользователя могли бы оказаться на разных шардах, и запросам по пользователю пришлось бы собирать данные со всего кластера.

## Часть 3. Наполнение и проверка распределения

Для генерации данных использовался скрипт:

```text
scripts/generate_clickstream.py
```

Данные вставлялись через распределённую таблицу `events_distributed`.

Всего было сгенерировано и вставлено:

```text
2 000 000 строк
```

Вставка выполнялась через `Distributed`-таблицу, поэтому ClickHouse сам распределял строки по шардам на основе ключа:

```sql
xxHash64(user_id)
```

После вставки была выполнена синхронизация реплик:

```sql
SYSTEM SYNC REPLICA idz4.events_local;
```

Результаты проверки сохранены в файле:

```text
checks/data_distribution.txt
```

### Общее количество строк

Проверка через `events_distributed`:

| total_rows |
|---:|
| 2000000 |

### Распределение по узлам

| Узел | rows |
|---|---:|
| `ch-s1-r1` | 1000608 |
| `ch-s1-r2` | 1000608 |
| `ch-s2-r1` | 999392 |
| `ch-s2-r2` | 999392 |

Внутри каждого шарда реплики содержат одинаковое количество строк:

- шард 1: `ch-s1-r1 = ch-s1-r2 = 1000608`;
- шард 2: `ch-s2-r1 = ch-s2-r2 = 999392`.

Между шардами данные распределились почти равномерно:

- шард 1 получил `1000608` строк;
- шард 2 получил `999392` строки.

Разница небольшая, поэтому ключ `xxHash64(user_id)` распределяет данные достаточно равномерно.

### Распределение пользователей

| Узел | unique_users | rows |
|---|---:|---:|
| `ch-s1-r1` | 250152 | 1000608 |
| `ch-s1-r2` | 250152 | 1000608 |
| `ch-s2-r1` | 249848 | 999392 |
| `ch-s2-r2` | 249848 | 999392 |

Количество уникальных пользователей между шардами также распределилось почти поровну.

### Проверка одного `user_id`

Была выполнена проверка нескольких пользователей:

| user_id | hosts | rows |
|---:|---|---:|
| 1 | `ch-s2-r1`, `ch-s2-r2` | 2 |
| 2 | `ch-s1-r1`, `ch-s1-r2` | 2 |
| 3 | `ch-s2-r2`, `ch-s2-r1` | 2 |
| 100 | `ch-s1-r2`, `ch-s1-r1` | 2 |
| 1000 | `ch-s2-r2`, `ch-s2-r1` | 2 |
| 7777 | `ch-s1-r2`, `ch-s1-r1` | 2 |

Каждый проверенный `user_id` оказался только на одном шарде, но на двух репликах этого шарда.  
Это подтверждает, что шардирование по `xxHash64(user_id)` работает предсказуемо.

## Часть 4. Запросы через Distributed

Для проверки работы распределённых запросов использовались таблицы:

* `events_local` — локальная таблица на `ReplicatedMergeTree`;
* `events_distributed` — распределённая таблица на `Distributed`;
* `user_dict` — локальная справочная таблица пользователей;
* `user_dict_distributed` — распределённая таблица для справочника пользователей.

SQL-запросы находятся в файлах:

```text
sql/03_user_dict.sql
sql/04_queries.sql
```

Результаты выполнения сохранены в файле:

```text
checks/distributed_queries.txt
```

### Глобальный COUNT

Запрос:

```sql
SELECT
    count() AS distributed_count
FROM idz4.events_distributed;
```

Результат:

| distributed_count |
| ----------------: |
|           2000000 |

Время выполнения:

```text
0.389 sec
```

Также была проверена сумма строк на локальных таблицах основных реплик шардов:

| Узел       |    rows |
| ---------- | ------: |
| `ch-s1-r1` | 1000608 |
| `ch-s2-r1` |  999392 |

Сумма локальных строк:

```text
2000000
```

Это совпадает с результатом запроса через `events_distributed`.

### GROUP BY с шардированным ключом

Запрос:

```sql
SELECT
    user_id,
    count() AS events_count,
    sum(duration_ms) AS total_duration_ms
FROM idz4.events_distributed
GROUP BY user_id
ORDER BY
    events_count DESC,
    user_id
LIMIT 10;
```

Результат:

| user_id | events_count | total_duration_ms |
| ------: | -----------: | ----------------: |
|       0 |            4 |               400 |
|       1 |            4 |               404 |
|       2 |            4 |               408 |
|       3 |            4 |               412 |
|       4 |            4 |               416 |
|       5 |            4 |               420 |
|       6 |            4 |               424 |
|       7 |            4 |               428 |
|       8 |            4 |               432 |
|       9 |            4 |               436 |

Время выполнения:

```text
1.677 sec
```

Этот запрос группирует данные по `user_id`.
Так как `user_id` используется в ключе шардирования `xxHash64(user_id)`, все события одного пользователя попадают на один шард. Поэтому агрегация по пользователю выполняется эффективно: ClickHouse не нужно собирать события одного пользователя с разных шардов.

### GROUP BY без шардированного ключа

Запрос:

```sql
SELECT
    page_url,
    count() AS visits,
    uniqExact(user_id) AS users_count,
    round(avg(duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed
GROUP BY page_url
ORDER BY
    visits DESC,
    page_url
LIMIT 10;
```

Результат:

| page_url    | visits | users_count | avg_duration_ms |
| ----------- | -----: | ----------: | --------------: |
| `/page/0`   |   2000 |         500 |            4600 |
| `/page/1`   |   2000 |         500 |            4601 |
| `/page/10`  |   2000 |         500 |            4610 |
| `/page/100` |   2000 |         500 |            4700 |
| `/page/101` |   2000 |         500 |            4701 |
| `/page/102` |   2000 |         500 |            4702 |
| `/page/103` |   2000 |         500 |            4703 |
| `/page/104` |   2000 |         500 |            4704 |
| `/page/105` |   2000 |         500 |            4705 |
| `/page/106` |   2000 |         500 |            4706 |

Время выполнения:

```text
0.883 sec
```

Здесь группировка выполняется по `page_url`, а это не ключ шардирования.
Поэтому одинаковые страницы могут встречаться на разных шардах, и ClickHouse должен объединять частичные результаты агрегации с разных шардов.

Такой запрос требует больше межшардовой обработки, чем группировка по `user_id`.

### JOIN со справочной таблицей

Для проверки JOIN была создана справочная таблица пользователей `user_dict`.

```sql
CREATE TABLE idz4.user_dict ON CLUSTER cluster_2x2 (
    user_id UInt64,
    name    String,
    segment LowCardinality(String)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/user_dict',
    '{replica}'
)
ORDER BY user_id;
```

Также была создана распределённая таблица:

```sql
CREATE TABLE idz4.user_dict_distributed ON CLUSTER cluster_2x2
AS idz4.user_dict
ENGINE = Distributed(
    'cluster_2x2',
    'idz4',
    'user_dict',
    xxHash64(user_id)
);
```

Справочник шардируется по тому же ключу `user_id`, что и таблица событий.

Запрос JOIN:

```sql
SELECT
    u.segment,
    count() AS events_count,
    uniqExact(e.user_id) AS users_count,
    round(avg(e.duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed AS e
INNER JOIN idz4.user_dict AS u
    ON e.user_id = u.user_id
GROUP BY u.segment
ORDER BY events_count DESC;
```

Результат:

| segment  | events_count | users_count | avg_duration_ms |
| -------- | -----------: | ----------: | --------------: |
| new      |       500000 |      125000 |            5098 |
| regular  |       500000 |      125000 |            5099 |
| inactive |       500000 |      125000 |            5101 |
| vip      |       500000 |      125000 |            5100 |

Время выполнения:

```text
1.870 sec
```

В данном случае `events` и `user_dict` шардируются по одному ключу `user_id`.
Это удобно, потому что данные пользователя и его события оказываются на одном шарде. Такой подход уменьшает необходимость пересылать большие объёмы данных между шардами.

Если справочная таблица маленькая, возможен другой подход — broadcast JOIN. В таком случае небольшая таблица или набор ключей рассылается на шарды.

### GLOBAL IN

Пример с `GLOBAL IN`:

```sql
SELECT
    count() AS vip_events
FROM idz4.events_distributed
WHERE user_id GLOBAL IN (
    SELECT user_id
    FROM idz4.user_dict_distributed
    WHERE segment = 'vip'
);
```

Результат:

| vip_events |
| ---------: |
|     500000 |

Время выполнения:

```text
0.631 sec
```

`GLOBAL IN` сначала строит набор значений, а затем передаёт его на шарды.
Это полезно, когда нужно отфильтровать большую распределённую таблицу по небольшому справочному набору.

### Вывод

`Distributed`-таблица позволяет выполнять запросы ко всему кластеру как к одной таблице.

Запросы по ключу шардирования `user_id` выполняются логично и предсказуемо, потому что данные одного пользователя находятся на одном шарде.

Запросы не по ключу шардирования, например группировка по `page_url`, требуют объединения частичных результатов с разных шардов.

JOIN лучше проектировать так, чтобы большие таблицы были шардированы по одному ключу. Если это невозможно, можно использовать подходы вроде `GLOBAL IN` или broadcast небольшого справочника.
