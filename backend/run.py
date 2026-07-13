import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent


def main():
    backend = subprocess.Popen(
        [str(ROOT_DIR / "myenv" / "bin" / "python3"), "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=ROOT_DIR / "agent",
    )

    try:
        backend.wait()
    except KeyboardInterrupt:
        print("Stopping backend...")
    finally:
        backend.terminate()
        backend.wait()


if __name__ == "__main__":
    main()
