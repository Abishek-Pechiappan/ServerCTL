import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent


def main():
    backend = subprocess.Popen(
        ["../myenv/bin/python3", "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=ROOT_DIR / "backend" / "agent",
    )
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=ROOT_DIR / "frontend" / "serverctl",
    )

    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        print("Stopping backend and frontend...")
    finally:
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()


if __name__ == "__main__":
    main()