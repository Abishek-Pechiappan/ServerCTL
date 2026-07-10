import getpass
import secrets
from pathlib import Path

ENV_PATH = Path(__file__).parent / "backend" / ".env"


def read_existing_secret_key() -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("JWT_SECRET_KEY="):
            return line.split("=", 1)[1]
    return None


def prompt_credentials() -> tuple[str, str]:
    username = input("Admin username: ").strip()
    while not username:
        username = input("Admin username: ").strip()

    while True:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password and password == confirm:
            return username, password
        print("Passwords empty or did not match, try again.")


def main():
    username, password = prompt_credentials()
    secret_key = read_existing_secret_key() or secrets.token_hex(32)

    ENV_PATH.write_text(
        f"ADMIN_USERNAME={username}\n"
        f"ADMIN_PASSWORD={password}\n"
        f"JWT_SECRET_KEY={secret_key}\n"
    )
    print(f"Wrote credentials to {ENV_PATH}")


if __name__ == "__main__":
    main()