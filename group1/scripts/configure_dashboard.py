import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DASHBOARD_FILE = (
    ROOT_DIR
    / "monitoring"
    / "dashboards"
    / "clickhouse.json"
)

CLICKHOUSE_DATASOURCE = {
    "type": "grafana-clickhouse-datasource",
    "uid": "clickhouse",
}


def sql_target(raw_sql: str) -> dict[str, Any]:
    return {
        "datasource": CLICKHOUSE_DATASOURCE,
        "editorType": "sql",
        "format": 1,
        "meta": {
            "builderOptions": {
                "columns": [],
                "database": "",
                "limit": 1000,
                "mode": "list",
                "queryType": "table",
                "table": "",
            }
        },
        "pluginVersion": "4.17.0",
        "queryType": "table",
        "rawSql": raw_sql.strip(),
        "refId": "A",
    }


def table_options() -> dict[str, Any]:
    return {
        "cellHeight": "sm",
        "footer": {
            "countRows": False,
            "enablePagination": False,
            "fields": "",
            "reducer": ["sum"],
            "show": False,
        },
        "showHeader": True,
        "sortBy": [],
    }


def configure_rows_panel(panel: dict[str, Any]) -> None:
    panel["title"] = "Rows by table (system.parts)"
    panel["description"] = (
        "Количество строк и активных частей по таблицам "
        "на всех ClickHouse-узлах."
    )
    panel["type"] = "table"
    panel["datasource"] = CLICKHOUSE_DATASOURCE
    panel["options"] = table_options()

    panel["fieldConfig"] = {
        "defaults": {
            "custom": {
                "align": "auto",
                "cellOptions": {
                    "type": "auto",
                },
                "inspect": False,
            },
            "mappings": [],
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {
                        "color": "green",
                        "value": None,
                    }
                ],
            },
        },
        "overrides": [],
    }

    panel["targets"] = [
        sql_target(
            """
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
    table
"""
        )
    ]


def configure_replicas_panel(panel: dict[str, Any]) -> None:
    panel["title"] = "Replication status (system.replicas)"
    panel["description"] = (
        "Состояние ReplicatedMergeTree на всех четырёх "
        "ClickHouse-узлах."
    )
    panel["type"] = "table"
    panel["datasource"] = CLICKHOUSE_DATASOURCE
    panel["options"] = table_options()

    panel["fieldConfig"] = {
        "defaults": {
            "custom": {
                "align": "auto",
                "cellOptions": {
                    "type": "auto",
                },
                "inspect": False,
            },
            "mappings": [],
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {
                        "color": "green",
                        "value": None,
                    }
                ],
            },
        },
        "overrides": [],
    }

    panel["targets"] = [
        sql_target(
            """
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
ORDER BY node
"""
        )
    ]


def main() -> None:
    dashboard = json.loads(
        DASHBOARD_FILE.read_text(encoding="utf-8")
    )

    found_rows_panel = False
    found_replicas_panel = False

    for panel in dashboard.get("panels", []):
        panel_id = panel.get("id")

        if panel_id == 1:
            configure_rows_panel(panel)
            found_rows_panel = True

        elif panel_id == 3:
            configure_replicas_panel(panel)
            found_replicas_panel = True

    if not found_rows_panel:
        raise RuntimeError(
            "Dashboard panel with id=1 was not found"
        )

    if not found_replicas_panel:
        raise RuntimeError(
            "Dashboard panel with id=3 was not found"
        )

    dashboard["version"] = (
        int(dashboard.get("version", 0)) + 1
    )

    DASHBOARD_FILE.write_text(
        json.dumps(
            dashboard,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Dashboard updated: {DASHBOARD_FILE}"
    )
    print(
        "Panel 1 uses system.parts through ClickHouse datasource"
    )
    print(
        "Panel 3 uses system.replicas through ClickHouse datasource"
    )


if __name__ == "__main__":
    main()