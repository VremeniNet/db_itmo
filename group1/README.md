# Групповая работа 1. HA-кластер ClickHouse 2x2 с мониторингом и балансировкой

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных

## Формат выполнения

Работа выполняется индивидуально.

Все компоненты инфраструктуры, конфигурация ClickHouse и Keeper, балансировка через Nginx, мониторинг Prometheus и Grafana, автоматизированные проверки и эксперименты с отказоустойчивостью выполняются одним студентом.

| Участник       | Зона ответственности                                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Желанов Даниил | ClickHouse-кластер, Keeper, Nginx, Prometheus, Grafana, генерация данных, Makefile, автоматизированные проверки и fault injection |


## Цель работы

Развернуть отказоустойчивый кластер ClickHouse с балансировщиком нагрузки, мониторингом и автоматизированными проверками.

Инфраструктура должна запускаться одной командой и включать:

* 4 узла ClickHouse: 2 шарда по 2 реплики;
* 3 узла ClickHouse Keeper;
* Nginx в роли HTTP-балансировщика;
* Prometheus для сбора метрик;
* Grafana с автоматически загружаемым дашбордом.

Всего используется 10 сервисов.

## Планируемая топология

```text
                         client
                            |
                         nginx
                            |
        +-------------------+-------------------+
        |                   |                   |
    ch-s1-r1            ch-s1-r2            ch-s2-r1
    shard 1             shard 1             shard 2
                                                |
                                            ch-s2-r2
                                            shard 2

        keeper1          keeper2          keeper3

                    prometheus + grafana
```

## Структура проекта

```text
group1/
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── config/
│   ├── clickhouse/
│   │   ├── cluster.xml
│   │   ├── prometheus.xml
│   │   ├── users.xml
│   │   └── macros.xml
│   ├── keeper/
│   │   └── keeper.xml
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── upstream.conf
│   └── prometheus/
│       └── prometheus.yml
├── monitoring/
│   ├── dashboards/
│   │   └── clickhouse.json
│   └── provisioning/
│       ├── datasources.yml
│       └── dashboards.yml
├── sql/
│   ├── 01_create_tables.sql
│   └── 02_test_queries.sql
├── scripts/
│   ├── generate_data.py
│   ├── fault_injection.py
│   └── run_tests.py
└── checks/
    ├── cluster_status.txt
    ├── data_distribution.txt
    ├── nginx_failover.txt
    ├── fault_scenarios.txt
    └── grafana_screenshots_NOT_ALLOWED.md
```
## Часть 1. Инфраструктура как код

Вся инфраструктура описана в файле:

```text
docker-compose.yml
```

Кластер состоит из 10 сервисов:

* 4 узла ClickHouse;
* 3 узла ClickHouse Keeper;
* Nginx;
* Prometheus;
* Grafana.

Для запуска используются переменные из файла `.env`. Пример настроек находится в `.env.example`.

Конфигурация шаблонизирована. В `docker-compose.yml` используются общие YAML-шаблоны:

```text
x-clickhouse-common
x-clickhouse-environment
x-keeper-common
```

Все ClickHouse-узлы используют одинаковые файлы конфигурации. Значения шарда, реплики и имени узла передаются через переменные окружения:

```text
CLICKHOUSE_SHARD
CLICKHOUSE_REPLICA
CLICKHOUSE_HOST
```

Единый файл `config/clickhouse/macros.xml` получает эти значения через `from_env`.

Для всех Keeper-узлов также используется один файл:

```text
config/keeper/keeper.xml
```

Уникальный `server_id` передаётся через переменную:

```text
KEEPER_SERVER_ID
```

Таким образом, в проекте нет четырёх копий одного ClickHouse-конфига и трёх копий одного Keeper-конфига.

Для управления инфраструктурой создан Makefile с командами:

```text
make up
make down
make status
make test
make logs
make restart
```

Команда `make test` запускает скрипт:

```text
scripts/run_tests.py
```

Скрипт проверяет:

* состояние всех 10 сервисов;
* доступность Nginx;
* выполнение ClickHouse-запроса через Nginx;
* готовность Prometheus;
* доступность Grafana.

Результат проверки сохраняется в:

```text
checks/cluster_status.txt
```

## Часть 2. ClickHouse-кластер

В конфигурации `remote_servers` создан кластер `production`.

Кластер содержит:

- 2 шарда;
- по 2 реплики в каждом шарде;
- всего 4 узла ClickHouse.

Топология:

| Шард | Реплика | Узел |
|---:|---:|---|
| 1 | 1 | `ch-s1-r1` |
| 1 | 2 | `ch-s1-r2` |
| 2 | 1 | `ch-s2-r1` |
| 2 | 2 | `ch-s2-r2` |

DDL находится в файле:

```text
sql/01_create_tables.sql
```

### Локальная таблица

Для физического хранения телеметрии создана таблица `ha.metrics_local`:

```sql
CREATE TABLE ha.metrics_local
ON CLUSTER production
(
    timestamp   DateTime,
    host        LowCardinality(String),
    metric_name LowCardinality(String),
    value       Float64
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/metrics_local',
    '{replica}'
)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (host, metric_name, timestamp);
```

Таблица содержит:

- `timestamp` — время измерения;
- `host` — источник телеметрии;
- `metric_name` — название метрики;
- `value` — числовое значение.

Путь в ClickHouse Keeper содержит макрос `{shard}`. Поэтому две реплики одного шарда используют общий журнал репликации.

Макрос `{replica}` отличается на каждом узле и задаёт уникальное имя реплики.

### Распределённая таблица

Поверх локальной таблицы создана таблица `ha.metrics_distributed`:

```sql
CREATE TABLE ha.metrics_distributed
ON CLUSTER production
AS ha.metrics_local
ENGINE = Distributed(
    'production',
    'ha',
    'metrics_local',
    xxHash64(host)
);
```

`metrics_distributed` сама не хранит данные. Она направляет вставки и запросы в локальные таблицы двух шардов.

Ключом шардирования выбран:

```sql
xxHash64(host)
```

Все измерения одного хоста попадают на один шард. Это удобно для запросов, группирующих телеметрию по источнику.

Внутри выбранного шарда данные копируются между двумя репликами с помощью `ReplicatedMergeTree`.

Проверочные запросы находятся в файле:

```text
sql/02_test_queries.sql
```

### Загрузка и распределение данных

Для генерации тестовой телеметрии использовался скрипт:

```text
scripts/generate_data.py
```

Через распределённую таблицу `ha.metrics_distributed` было загружено:

```text
5 000 000 строк
```

Вставка выполнялась с настройкой:

```sql
SET insert_distributed_sync = 1;
```

После вставки была принудительно очищена очередь `Distributed`:

```sql
SYSTEM FLUSH DISTRIBUTED ha.metrics_distributed;
```

Затем на всех четырёх узлах была выполнена синхронизация реплик:

```sql
SYSTEM SYNC REPLICA ha.metrics_local;
```

Результаты проверки сохранены в файле:

```text
checks/data_distribution.txt
```

Время загрузки данных:

```text
12.268 sec
```

### Глобальное количество строк

Запрос через распределённую таблицу:

```sql
SELECT count()
FROM ha.metrics_distributed;
```

вернул:

| distributed_rows |
|---:|
| 5000000 |

### Распределение по шардам и репликам

| Узел | Шард | Строки | Уникальные хосты |
|---|---:|---:|---:|
| `ch-s1-r1` | 1 | 2500800 | 50016 |
| `ch-s1-r2` | 1 | 2500800 | 50016 |
| `ch-s2-r1` | 2 | 2499200 | 49984 |
| `ch-s2-r2` | 2 | 2499200 | 49984 |

Реплики внутри каждого шарда содержат одинаковое количество строк:

- `ch-s1-r1 = ch-s1-r2 = 2500800`;
- `ch-s2-r1 = ch-s2-r2 = 2499200`.

Сумма одной реплики от каждого шарда:

```text
2500800 + 2499200 = 5000000
```

Данные распределились почти равномерно. Разница между шардами составила только `1600` строк.

### Состояние репликации

На всех четырёх узлах получены одинаковые основные показатели:

| Показатель | Значение |
|---|---:|
| `total_replicas` | 2 |
| `active_replicas` | 2 |
| `queue_size` | 0 |
| `inserts_in_queue` | 0 |
| `merges_in_queue` | 0 |

Значение `active_replicas = 2` означает, что обе реплики каждого шарда доступны.

Значение `queue_size = 0` означает, что все задачи репликации обработаны и отставания между репликами нет.

### Проверка ключа шардирования

Ключом шардирования является:

```sql
xxHash64(host)
```

Проверка нескольких хостов показала:

| Хост | Шард | Строки на каждой реплике |
|---|---:|---:|
| `host-000002` | 1 | 50 |
| `host-010000` | 1 | 50 |
| `host-000001` | 2 | 50 |
| `host-000003` | 2 | 50 |
| `host-001000` | 2 | 50 |
| `host-099999` | 2 | 50 |

Каждый хост присутствует только на одном шарде. При этом его данные есть на обеих репликах выбранного шарда.

Это подтверждает, что шардирование по `host` работает предсказуемо, а репликация внутри шарда работает корректно.

### Аналитический запрос

Через таблицу `metrics_distributed` была выполнена агрегация по типам метрик:

| metric_name | measurements | avg_value | min_value | max_value |
|---|---:|---:|---:|---:|
| `cpu_usage` | 1000000 | 49.98 | 0 | 99.95 |
| `disk_usage` | 1000000 | 54.97 | 10.02 | 99.97 |
| `memory_usage` | 1000000 | 89.96 | 20.01 | 159.96 |
| `network_in` | 1000000 | 25000.05 | 0.3 | 49999.8 |
| `network_out` | 1000000 | 19600.15 | 0.4 | 39999.9 |

Распределённая таблица корректно объединила данные с обоих шардов и вернула результат по всем пяти миллионам строк.