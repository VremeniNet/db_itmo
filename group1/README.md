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

## Часть 3. Nginx как HTTP-балансировщик

Для балансировки HTTP-запросов к ClickHouse используется Nginx.

Конфигурация находится в файлах:

```text
config/nginx/nginx.conf
config/nginx/upstream.conf
```

Nginx принимает запросы на порту:

```text
8085
```

и проксирует их на HTTP-интерфейсы четырёх ClickHouse-узлов:

- `ch-s1-r1:8123`;
- `ch-s1-r2:8123`;
- `ch-s2-r1:8123`;
- `ch-s2-r2:8123`.

Для upstream не указана отдельная стратегия балансировки, поэтому используется стандартный алгоритм round-robin.

Конфигурация серверов:

```nginx
upstream clickhouse_http {
    server ch-s1-r1:8123 max_fails=2 fail_timeout=10s;
    server ch-s1-r2:8123 max_fails=2 fail_timeout=10s;
    server ch-s2-r1:8123 max_fails=2 fail_timeout=10s;
    server ch-s2-r2:8123 max_fails=2 fail_timeout=10s;

    keepalive 32;
}
```

Параметры `max_fails` и `fail_timeout` реализуют пассивную проверку доступности. Если запросы к узлу несколько раз завершаются ошибкой, Nginx временно исключает его из балансировки.

Также настроен повтор запроса на другом upstream:

```nginx
proxy_next_upstream
    error
    timeout
    invalid_header
    http_500
    http_502
    http_503
    http_504;

proxy_next_upstream_tries 4;
```

### Проверка round-robin

Для автоматизированной проверки использовался скрипт:

```text
scripts/nginx_failover.py
```

Результат сохранён в файле:

```text
checks/nginx_failover.txt
```

До остановки узла было выполнено 16 запросов:

```sql
SELECT hostName();
```

Распределение:

| Узел | Количество запросов |
|---|---:|
| `ch-s1-r1` | 4 |
| `ch-s1-r2` | 4 |
| `ch-s2-r1` | 4 |
| `ch-s2-r2` | 4 |

Это подтверждает равномерную работу round-robin.

### Отказ одной реплики

Во время эксперимента был остановлен контейнер:

```text
group1-ch-s1-r2
```

После остановки было выполнено ещё 20 запросов через Nginx.

Результат:

| Узел | Количество запросов |
|---|---:|
| `ch-s1-r1` | 6 |
| `ch-s2-r1` | 8 |
| `ch-s2-r2` | 6 |

Узел `ch-s1-r2` отсутствовал в успешных ответах, а все клиентские запросы завершились без ошибки.

Распределённый запрос во время отказа:

```sql
SELECT count()
FROM ha.metrics_distributed;
```

вернул:

```text
5000000
```

Это означает, что потеря одной реплики не нарушила доступность данных.

### Пассивная проверка доступности

В access-логе Nginx был зафиксирован запрос к остановленному узлу:

```text
upstream_status: 504, 200
```

Сначала соединение с недоступным upstream завершилось по таймауту, после чего Nginx повторил запрос на другом ClickHouse-узле.

Итоговый HTTP-статус для клиента:

```text
200
```

Также Nginx записал сообщение:

```text
upstream server temporarily disabled
```

Это подтверждает, что после нескольких неудачных соединений остановленный узел был временно исключён из балансировки.

Access-лог сохраняется в JSON-формате и содержит:

- время запроса;
- адрес клиента;
- HTTP-запрос;
- итоговый статус;
- время выполнения;
- адрес upstream;
- статус upstream;
- время ответа upstream.

### Восстановление узла

После запуска `group1-ch-s1-r2` и завершения `fail_timeout` узел снова появился в round-robin.

Распределение 16 запросов после восстановления:

| Узел | Количество запросов |
|---|---:|
| `ch-s1-r1` | 4 |
| `ch-s1-r2` | 4 |
| `ch-s2-r1` | 5 |
| `ch-s2-r2` | 3 |

Небольшое отличие от идеального распределения связано с текущим положением round-robin и временным исключением восстановленного upstream.

Эксперимент подтвердил, что Nginx продолжает обслуживать запросы при потере одного ClickHouse-узла и автоматически возвращает восстановленный узел в балансировку.

## Часть 4. Мониторинг

Для мониторинга кластера используются:

- Prometheus;
- Grafana;
- встроенный Prometheus-эндпоинт ClickHouse;
- официальный Grafana ClickHouse datasource.

Prometheus доступен на порту:

```text
9095
```

Grafana доступна на порту:

```text
3005
```

### Сбор метрик ClickHouse

На каждом ClickHouse-узле включён встроенный Prometheus-эндпоинт:

```text
/metrics
```

Prometheus собирает метрики с четырёх адресов:

```text
ch-s1-r1:9363
ch-s1-r2:9363
ch-s2-r1:9363
ch-s2-r2:9363
```

Проверка показала, что все четыре target имеют состояние:

```text
health = up
```

PromQL-запрос:

```promql
sum(up{job="clickhouse"})
```

вернул:

```text
4
```

Это означает, что Prometheus успешно собирает метрики со всех четырёх ClickHouse-узлов.

### Источники данных Grafana

Grafana автоматически получает два datasource через provisioning:

- `Prometheus`;
- `ClickHouse`.

Prometheus datasource используется для временных рядов и технических метрик.

ClickHouse datasource используется для SQL-запросов к системным таблицам:

- `system.parts`;
- `system.replicas`.

ClickHouse datasource настроен для подключения к:

```text
ch-s1-r1:8123
```

Проверка datasource через Grafana API вернула:

```text
status: OK
message: Data source is working
```

### Автоматическое provisioning

Конфигурация datasource находится в файле:

```text
monitoring/provisioning/datasources.yml
```

Конфигурация загрузки дашбордов находится в файле:

```text
monitoring/provisioning/dashboards.yml
```

Дашборд экспортирован в JSON:

```text
monitoring/dashboards/clickhouse.json
```

После запуска Grafana дашборд `ClickHouse HA Cluster` появляется автоматически. Ручная настройка через веб-интерфейс не требуется.

### Панели дашборда

Дашборд содержит пять панелей.

#### 1. Количество строк по таблицам

Источник данных:

```text
ClickHouse
```

Панель выполняет SQL-запрос к `system.parts`:

```sql
SELECT
    hostName() AS node,
    database,
    table,
    sum(rows) AS rows,
    count() AS active_parts
FROM clusterAllReplicas(
    'production',
    system.parts
)
WHERE active
  AND database = 'ha'
GROUP BY
    node,
    database,
    table
ORDER BY
    node,
    database,
    table;
```

Фактическое количество строк:

| Узел | Таблица | Строки | Активные части |
|---|---|---:|---:|
| `ch-s1-r1` | `metrics_local` | 2500800 | 3 |
| `ch-s1-r2` | `metrics_local` | 2500800 | 3 |
| `ch-s2-r1` | `metrics_local` | 2499200 | 3 |
| `ch-s2-r2` | `metrics_local` | 2499200 | 3 |

#### 2. Количество запросов в секунду

Источник данных:

```text
Prometheus
```

PromQL:

```promql
rate(ClickHouseProfileEvents_Query{job="clickhouse"}[1m])
```

Панель показывает интенсивность запросов отдельно для каждого ClickHouse-узла.

#### 3. Статус репликации

Источник данных:

```text
ClickHouse
```

Панель выполняет запрос к `system.replicas`:

```sql
SELECT
    hostName() AS node,
    database,
    table,
    replica_name,
    total_replicas,
    active_replicas,
    queue_size,
    inserts_in_queue,
    merges_in_queue,
    absolute_delay
FROM clusterAllReplicas(
    'production',
    system.replicas
)
WHERE database = 'ha'
  AND table = 'metrics_local'
ORDER BY node;
```

На всех четырёх узлах получены значения:

| Показатель | Значение |
|---|---:|
| `total_replicas` | 2 |
| `active_replicas` | 2 |
| `queue_size` | 0 |
| `absolute_delay` | 0 |

Это означает, что реплики синхронизированы и не имеют отставания.

#### 4. Использование памяти

Источник данных:

```text
Prometheus
```

PromQL:

```promql
ClickHouseMetrics_MemoryTracking{job="clickhouse"}
```

Панель показывает память, используемую каждым ClickHouse-узлом.

#### 5. Количество доступных ClickHouse-узлов

Источник данных:

```text
Prometheus
```

PromQL:

```promql
sum(up{job="clickhouse"})
```

В нормальном состоянии панель показывает:

```text
4
```

### Автоматизированная проверка

Для проверки мониторинга используется скрипт:

```text
scripts/check_monitoring.py
```

Результат сохраняется в файле:

```text
checks/monitoring_status.txt
```

Скрипт проверяет:

- состояние Prometheus targets;
- доступность всех ClickHouse-узлов;
- наличие метрик QPS, памяти и репликации;
- реальные данные из `system.parts`;
- реальные данные из `system.replicas`;
- состояние Grafana;
- состояние ClickHouse datasource;
- наличие provisioned-дашборда;
- наличие всех требуемых панелей.

## Часть 5. Отказоустойчивость

Для проверки отказоустойчивости были проведены четыре сценария:

| Сценарий              | Действие                            | Фактический результат                                             |
| --------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| Потеря реплики        | Остановлен `ch-s1-r2`               | Запросы через Nginx продолжают выполняться                        |
| Потеря шарда          | Остановлены `ch-s2-r1` и `ch-s2-r2` | Локальное чтение работает, Distributed-запрос завершается ошибкой |
| Потеря одного Keeper  | Остановлен `keeper1`                | Кворум сохраняется, INSERT выполняется                            |
| Потеря Keeper-кворума | Остановлены `keeper1` и `keeper2`   | INSERT невозможен, локальный SELECT работает                      |

Результаты сохранены в файлах:

```text
checks/nginx_failover.txt
checks/fault_scenarios.txt
```

Автоматизация экспериментов находится в скриптах:

```text
scripts/nginx_failover.py
scripts/fault_injection.py
```

### Сценарий 1. Потеря одной ClickHouse-реплики

Был остановлен контейнер:

```text
group1-ch-s1-r2
```

До остановки Nginx равномерно распределил 16 запросов:

| Узел       | Запросы |
| ---------- | ------: |
| `ch-s1-r1` |       4 |
| `ch-s1-r2` |       4 |
| `ch-s2-r1` |       4 |
| `ch-s2-r2` |       4 |

После остановки реплики было выполнено 20 запросов.

Все запросы завершились успешно через оставшиеся узлы:

| Узел       | Запросы |
| ---------- | ------: |
| `ch-s1-r1` |       6 |
| `ch-s2-r1` |       8 |
| `ch-s2-r2` |       6 |

Запрос к распределённой таблице продолжил возвращать:

```text
5000000
```

В JSON access-логе Nginx был зафиксирован переход с недоступного upstream на работающий:

```text
upstream_status: 504, 200
```

Итоговый HTTP-статус для клиента остался:

```text
200
```

После восстановления `ch-s1-r2` узел снова появился в round-robin.

### Сценарий 2. Потеря целого шарда

Были остановлены обе реплики второго шарда:

```text
group1-ch-s2-r1
group1-ch-s2-r2
```

Локальный запрос к первому шарду продолжил работать:

```text
node       local_rows
ch-s1-r1   2500800
```

Запрос через `ha.metrics_distributed` завершился ошибкой:

```text
ALL_CONNECTION_TRIES_FAILED
```

Причина заключается в том, что для получения полного результата ClickHouse должен обратиться к обоим шардам, но обе реплики второго шарда были недоступны.

После восстановления `ch-s2-r1` и `ch-s2-r2` распределённый запрос снова вернул:

```text
5000000
```

Также была выполнена проверка временной реплицированной таблицы. Все четыре реплики вернулись в рабочее состояние:

```text
is_readonly = 0
active_replicas = 2
queue_size = 0
```

### Сценарий 3. Потеря одного Keeper

Перед экспериментом Keeper-кластер состоял из:

* одного лидера;
* двух followers.

После остановки `keeper1` оставшиеся узлы выбрали лидером `keeper3`.

Состояние кворума:

```text
keeper2: follower
keeper3: leader
zk_synced_followers: 1
```

Два из трёх Keeper оставались доступными, поэтому кворум сохранялся.

Вставка в реплицированную тестовую таблицу завершилась успешно:

```text
Return code: 0
INSERT succeeded
```

Тестовая строка была направлена на второй шард и появилась на обеих его репликах:

| Узел       | rows | one_keeper_down_rows |
| ---------- | ---: | -------------------: |
| `ch-s2-r1` |    1 |                    1 |
| `ch-s2-r2` |    1 |                    1 |

Это подтверждает, что потеря одного Keeper не нарушает запись и репликацию данных.

Во время эксперимента одна из реплик первого шарда временно находилась в режиме `readonly`, однако тестовая вставка на втором шарде завершилась и была реплицирована корректно. После восстановления Keeper все сервисы вернулись в рабочее состояние.

### Сценарий 4. Потеря Keeper-кворума

Были остановлены два Keeper:

```text
group1-keeper1
group1-keeper2
```

Доступным остался только `keeper3`.

Команда `ruok` возвращала:

```text
imok
```

Это означает, что процесс Keeper запущен, но одного узла недостаточно для кворума из трёх участников.

Попытка вставки в `ReplicatedMergeTree` не завершилась:

```text
Return code: 124
TIMEOUT after 25 seconds
```

Зависший запрос был отправлен на отмену:

```sql
KILL QUERY
WHERE query_id = 'fault_no_quorum_...'
ASYNC;
```

Проверка до восстановления Keeper показала:

```text
no_quorum_rows
0
```

При этом чтение существующих локальных данных продолжило работать:

```text
node       local_metrics_rows
ch-s1-r1   2500800
```

После восстановления Keeper-кворума тестовая строка так и не появилась:

| Узел       | no_quorum_rows |
| ---------- | -------------: |
| `ch-s1-r1` |              0 |
| `ch-s1-r2` |              0 |
| `ch-s2-r1` |              0 |
| `ch-s2-r2` |              0 |

Это подтверждает ожидаемое поведение:

* без Keeper-кворума новые записи в `ReplicatedMergeTree` невозможны;
* существующие локальные данные остаются доступными для чтения;
* отменённая вставка не была применена после восстановления кворума.

### Восстановление после экспериментов

После завершения всех сценариев были запущены:

* все три Keeper;
* все четыре ClickHouse-узла.

Каждый ClickHouse-контейнер прошёл проверку:

```sql
SELECT 1;
```

Итоговое количество основных данных не изменилось:

```text
distributed_rows
5000000
```

Временные таблицы `fault_test_local` и `fault_test_distributed` были удалены.

### Вывод

Кластер выдерживает потерю одной ClickHouse-реплики без нарушения доступности запросов.

Потеря целого шарда делает недоступной часть распределённых данных, поэтому запрос через `Distributed` завершается ошибкой. После восстановления шарда полная доступность возвращается.

Keeper-кластер сохраняет возможность записи при потере одного узла, поскольку два оставшихся узла образуют кворум.

При потере двух Keeper запись в реплицированные таблицы становится невозможной, но чтение уже существующих локальных данных продолжает работать.
