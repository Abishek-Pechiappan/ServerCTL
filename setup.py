import getpass
import json
import secrets
from pathlib import Path

ENV_PATH = Path(__file__).parent / "backend" / ".env"


def read_existing_value(key: str) -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return None


def prompt_credentials() -> tuple[str, str]:
    existing_user = read_existing_value("ADMIN_USERNAME")
    existing_pass = read_existing_value("ADMIN_PASSWORD")
    if existing_user and existing_pass:
        keep = input(
            f"Admin credentials already set for '{existing_user}'. Keep them? [Y/n]: "
        ).strip().lower()
        if keep in ("", "y", "yes"):
            return existing_user, existing_pass

    username = input("Admin username: ").strip()
    while not username:
        username = input("Admin username: ").strip()

    while True:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password and password == confirm:
            return username, password
        print("Passwords empty or did not match, try again.")


def prompt_login_webhook() -> str:
    existing = read_existing_value("N8N_LOGIN_WEBHOOK_URL")
    suffix = f" [{existing}]" if existing else ""
    webhook = input(
        f"n8n SSH login webhook URL (optional, press enter to skip){suffix}: "
    ).strip()
    return webhook or existing or ""


def main():
    username, password = prompt_credentials()
    secret_key = read_existing_value("JWT_SECRET_KEY") or secrets.token_hex(32)
    login_webhook = prompt_login_webhook()

    env_contents = (
        f"ADMIN_USERNAME={username}\n"
        f"ADMIN_PASSWORD={password}\n"
        f"JWT_SECRET_KEY={secret_key}\n"
    )
    if login_webhook:
        env_contents += f"N8N_LOGIN_WEBHOOK_URL={login_webhook}\n"

    ENV_PATH.write_text(env_contents)
    print(f"Wrote credentials to {ENV_PATH}")

    if login_webhook:
        print()
        print("n8n Webhook node setup:")
        print("  HTTP Method: POST")
        print(f"  URL: {login_webhook}")
        print("  Payload sent on each new SSH login:")
        print(json.dumps(
            {
                "event": "ssh_login",
                "user": "shek",
                "tty": "pts/0",
                "host": None,
                "login_time": "2026-07-17T14:20:11+00:00",
                "logout_time": None,
                "still_logged_in": True,
            },
            indent=2,
        ))


if __name__ == "__main__":
    main()