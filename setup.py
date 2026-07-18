import getpass
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent / "backend"
ENV_PATH = BACKEND_DIR / ".env"

sys.path.insert(0, str(BACKEND_DIR))
from password import hash_password  # noqa: E402  (needs BACKEND_DIR on sys.path)


def read_existing_value(key: str) -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return None


def prompt_credentials() -> tuple[str, str]:
    """Return (username, password_hash)."""
    existing_user = read_existing_value("ADMIN_USERNAME")
    existing_hash = read_existing_value("ADMIN_PASSWORD_HASH")
    if existing_user and existing_hash:
        keep = input(
            f"Admin credentials already set for '{existing_user}'. Keep them? [Y/n]: "
        ).strip().lower()
        if keep in ("", "y", "yes"):
            return existing_user, existing_hash

    username = input("Admin username: ").strip()
    while not username:
        username = input("Admin username: ").strip()

    while True:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password and password == confirm:
            return username, hash_password(password)
        print("Passwords empty or did not match, try again.")


def main():
    username, password_hash = prompt_credentials()
    secret_key = read_existing_value("JWT_SECRET_KEY") or secrets.token_hex(32)

    env_contents = (
        f"ADMIN_USERNAME={username}\n"
        f"ADMIN_PASSWORD_HASH={password_hash}\n"
        f"JWT_SECRET_KEY={secret_key}\n"
    )

    ENV_PATH.write_text(env_contents)
    print(f"Wrote credentials to {ENV_PATH}")


if __name__ == "__main__":
    main()
