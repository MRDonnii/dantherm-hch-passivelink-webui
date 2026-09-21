"""Build one bounded, redacted text report from allowlisted Pi diagnostics."""
from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import time
from pathlib import Path

MAX_SECTION_BYTES = 512 * 1024
REDACTIONS = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:token|password|passwd|secret|authorization|cookie)(?:[-_ ]?(?:key|value))?[\"']?\s*[:=]\s*)(?!\[REDACTED\])(?:\"[^\"]*\"|'[^']*'|\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?im)^([^\n=]*(?:token|password|passwd|secret|authorization|cookie)[^\n=]*=).*$"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(dantherm_session=)[^;\s]+"), r"\1[REDACTED]"),
)


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def run_command(command: tuple[str, ...], timeout: int = 8) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        text = result.stdout
        if result.stderr:
            text += ("\n" if text else "") + "[stderr]\n" + result.stderr
        text += f"\n[exit_code={result.returncode}]\n"
    except (OSError, subprocess.SubprocessError) as error:
        text = f"Unavailable: {type(error).__name__}: {error}\n"
    encoded = text.encode("utf-8", "replace")
    if len(encoded) > MAX_SECTION_BYTES:
        text = "[older output truncated]\n" + encoded[-MAX_SECTION_BYTES:].decode("utf-8", "replace")
    return redact(text)


def read_file(path: str, limit: int = 128 * 1024) -> str:
    try:
        return redact(Path(path).read_text(encoding="utf-8", errors="replace")[:limit])
    except OSError as error:
        return f"Unavailable: {type(error).__name__}: {error}\n"


def build_report(services: dict[str, str]) -> tuple[bytes, str]:
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    sections: list[tuple[str, str]] = [
        ("REPORT", json.dumps({
            "format_version": 1, "created_utc": created, "hostname": socket.gethostname(),
            "os": platform.platform(), "python": platform.python_version(), "services": services,
            "privacy": "Known credentials, tokens, cookies and authorization values are redacted. Review before sharing."
        }, indent=2, ensure_ascii=False)),
        ("OS RELEASE", read_file("/etc/os-release")),
        ("UPTIME", run_command(("/usr/bin/uptime",))),
        ("MEMORY", run_command(("/usr/bin/free", "-h"))),
        ("DISK", run_command(("/usr/bin/df", "-hT"))),
        ("BLOCK DEVICES", run_command(("/usr/bin/lsblk", "-o", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,RO"))),
        ("MOUNTS", read_file("/proc/mounts")),
        ("FAILED UNITS", run_command(("/usr/bin/systemctl", "--failed", "--no-pager", "--plain"))),
        ("SERVICE STATUS", run_command(("/usr/bin/systemctl", "show", *services.values(), "-p", "Id", "-p", "ActiveState", "-p", "SubState", "-p", "Result", "-p", "MainPID", "-p", "NRestarts", "-p", "MemoryCurrent"))),
        ("SYSTEM WARNINGS - LAST 7 DAYS", run_command(("/usr/bin/journalctl", "--since", "-7 days", "-p", "warning..alert", "--no-pager", "-n", "1000", "-o", "short-iso"))),
        ("KERNEL WARNINGS - CURRENT BOOT", run_command(("/usr/bin/journalctl", "-k", "-b", "-p", "warning..alert", "--no-pager", "-n", "500", "-o", "short-iso"))),
        ("NETWORK ADDRESS", run_command(("/usr/sbin/ip", "address"))),
        ("NETWORK ROUTES", run_command(("/usr/sbin/ip", "route"))),
    ]
    for label, service in services.items():
        sections.append((f"JOURNAL - {label.upper()} - LAST 7 DAYS", run_command(("/usr/bin/journalctl", "--since", "-7 days", "-u", service, "--no-pager", "-n", "1000", "-o", "short-iso"))))
    if os.path.exists("/usr/bin/vcgencmd"):
        sections.extend((
            ("RASPBERRY PI THROTTLING", run_command(("/usr/bin/vcgencmd", "get_throttled"))),
            ("RASPBERRY PI TEMPERATURE", run_command(("/usr/bin/vcgencmd", "measure_temp"))),
        ))
    report = "\n\n".join(f"{'=' * 20} {title} {'=' * 20}\n{body.rstrip()}" for title, body in sections) + "\n"
    return report.encode("utf-8"), f"dantherm-debug-{stamp}.txt"
