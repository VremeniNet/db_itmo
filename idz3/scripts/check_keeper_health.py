from pathlib import Path
import socket


KEEPERS = [
    ("keeper1", "127.0.0.1", 9181),
    ("keeper2", "127.0.0.1", 9182),
    ("keeper3", "127.0.0.1", 9183),
]


def send_4lw_command(host: str, port: int, command: str) -> str:
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall((command + "\n").encode("utf-8"))

        chunks = []
        sock.settimeout(5)

        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break

            if not data:
                break

            chunks.append(data)

    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    output_file = project_dir / "checks" / "keeper_health.txt"

    lines = []
    lines.append("ClickHouse Keeper health check")
    lines.append("")

    for keeper_name, host, port in KEEPERS:
        lines.append("=" * 60)
        lines.append(f"{keeper_name} ({host}:{port})")
        lines.append("=" * 60)
        lines.append("")

        lines.append("Command: ruok")
        try:
            ruok_result = send_4lw_command(host, port, "ruok")
        except Exception as error:
            ruok_result = f"ERROR: {error}"
        lines.append(ruok_result)
        lines.append("")

        lines.append("Command: mntr")
        try:
            mntr_result = send_4lw_command(host, port, "mntr")
        except Exception as error:
            mntr_result = f"ERROR: {error}"
        lines.append(mntr_result)
        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()