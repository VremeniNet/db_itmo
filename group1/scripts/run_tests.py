import subprocess
import sys
import time
import urllib.request
from pathlib import Path

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "cluster_status.txt"

EXPECTED_SERVICES = {
    "keeper1",
    "keeper2",
    "keeper3",
    "ch-s1-r1",
    "ch-s1-r2",
    "ch-s2-r1",
    "ch-s2-r2",
    "nginx",
    "prometheus",
    "grafana",
}

HTTP_CHECKS = {
    "Nginx health": "http://127.0.0.1:8085/health",
    "ClickHouse through Nginx": (
        "http://127.0.0.1:8085/"
        "?query=SELECT%201%20FORMAT%20TabSeparated"
    ),
    "Prometheus readiness": "http://127.0.0.1:9095/-/ready",
    "Grafana health": "http://127.0.0.1:3005/api/health",
}


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout.strip()


def get_url(url: str, attempts: int = 10) -> str:
    last_error = ""

    for _ in range(attempts):
        try:
            with NO_PROXY_OPENER.open(url, timeout=5) as response:
                return response.read().decode("utf-8", errors="replace").strip()
        except Exception as error:
            last_error = str(error)
            time.sleep(2)

    raise RuntimeError(last_error)


def main() -> None:
    lines: list[str] = []
    failed = False

    lines.append("HA cluster automated status check")
    lines.append("")

    code, services_output = run(
        ["docker", "compose", "ps", "--services", "--status", "running"]
    )

    running_services = {
        line.strip()
        for line in services_output.splitlines()
        if line.strip()
    }

    lines.append("Running services:")
    lines.extend(sorted(running_services))
    lines.append("")

    missing = EXPECTED_SERVICES - running_services

    if code != 0 or missing:
        failed = True
        lines.append(f"Missing services: {sorted(missing)}")
    else:
        lines.append("All 10 services are running.")

    lines.append("")

    for name, url in HTTP_CHECKS.items():
        lines.append(f"{name}:")
        lines.append(f"URL: {url}")

        try:
            response = get_url(url)
            lines.append(f"Result: {response}")
        except Exception as error:
            failed = True
            lines.append(f"ERROR: {error}")

        lines.append("")

    code, compose_status = run(["docker", "compose", "ps"])
    lines.append("docker compose ps:")
    lines.append(compose_status)
    lines.append("")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()