import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent


def ensure_npm():
    if shutil.which("npm"):
        return
    print("npm not found, installing nodejs/npm via apt...")
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "nodejs", "npm"], check=True)


def main():
    backend_dir = ROOT_DIR / "backend"
    venv_dir = backend_dir / "myenv"

    if not (venv_dir / "bin" / "python3").exists():
        subprocess.run([sys.executable, "-m", "venv", "myenv"], cwd=backend_dir, check=True)

    subprocess.run(
        ["myenv/bin/python3", "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=backend_dir,
        check=True,
    )

    ensure_npm()
    subprocess.run(
        ["npm", "install"],
        cwd=ROOT_DIR / "frontend" / "serverctl",
        check=True,
    )


if __name__ == "__main__":
    main()