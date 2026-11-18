"""Demo-account password handling. No password is ever stored in the code or the repository.

The password comes from the NACB_DEMO_PASSWORD environment variable. When it is not set (e.g. on a developer's
laptop) a strong random password is generated once and kept in demo-credentials.local.txt, which git ignores."""
import os
import secrets
from pathlib import Path

LOCAL_FILE = Path(__file__).resolve().parent.parent / "demo-credentials.local.txt"


def demo_password():
    value = os.environ.get("NACB_DEMO_PASSWORD", "").strip()
    if value:
        return value
    if LOCAL_FILE.exists():
        for line in LOCAL_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    value = "Nacb-" + secrets.token_urlsafe(12) + "9!"
    LOCAL_FILE.write_text(
        "# NACB demo accounts (development only). This file is ignored by git: never commit or share it publicly.\n"
        "# Accounts: admin@nacb.test, officer@nacb.test, approver@nacb.test, district@nacb.test, committee@nacb.test,\n"
        "#           artist@nacb.test, newartist@nacb.test, org@nacb.test, round1-0..3@nacb.test\n"
        f"password={value}\n", encoding="utf-8")
    return value
