import os
import subprocess
import sys
from datetime import datetime
from config import PROJECT_ROOT, EMAIL_TO
from email_sender import send_failure_alert


def _get_recent_logs(lines_count: int = 45) -> str:
    """Attempt to get the last lines from journalctl, falling back to digest13.log."""
    try:
        cmd = ["journalctl", "--user", "-u", "digest13.service", "-n", str(lines_count), "--no-pager"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    # Fallback to logs/digest13.log if journalctl isn't available
    log_file = PROJECT_ROOT / "logs" / "digest13.log"
    if log_file.exists():
        try:
            content = log_file.read_text(encoding="utf-8").strip().splitlines()
            return "\n".join(content[-lines_count:])
        except Exception:
            pass

    return "No se pudieron obtener los registros de ejecución."


def main() -> None:
    exit_info = sys.argv[1] if len(sys.argv) > 1 else "desconocido"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_stamp = datetime.now().strftime("%Y.%m.%d")

    subject = f"Digest 13 ⚠️ Error en la ejecución — {date_stamp}"
    logs = _get_recent_logs(40)

    header = f"Fecha y hora: {now_str}\nInformación de salida: {exit_info}\n\n--- ÚLTIMOS REGISTROS ---\n"
    full_error_text = header + logs

    print(f"[{now_str}] Enviando alerta de fallo por correo a {EMAIL_TO}...")
    try:
        send_failure_alert(subject, full_error_text)
        print(f"[{now_str}] Correo de alerta de fallo enviado exitosamente.")
    except Exception as e:
        print(f"[{now_str}] ERROR al enviar correo de alerta de fallo: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
