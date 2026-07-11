import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent


def main():
    subprocess.run(
        ["myenv/bin/python3", "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=ROOT_DIR / "backend",
        check=True,
    )
    subprocess.run(
        ["npm", "install"],
        cwd=ROOT_DIR / "frontend" / "serverctl",
        check=True,
    )


if __name__ == "__main__":
    main()