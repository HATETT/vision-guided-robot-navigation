import os
import sys
import time
import signal
import subprocess
from pathlib import Path
import requests  

from src.vision_guided_robot_navigation.orchestration.app.bootstrap import run_workcell

REPO_ROOT = Path(__file__).resolve().parent

VISION_CONDA_ENV = os.getenv("VISION_CONDA_ENV", "vision313")
VISION_HOST = os.getenv("VISION_HOST", "127.0.0.1")
VISION_PORT = int(os.getenv("VISION_PORT", "8010"))
VISION_HEALTH_URL = f"http://{VISION_HOST}:{VISION_PORT}/health"

# Запускается vision в py313 env:
VISION_MODULE = os.getenv("VISION_MODULE", "vision_service.orchestration.app.bootstrap")

def _start_vision() -> subprocess.Popen:
    cmd = [
        "conda", "run",
        "-n", VISION_CONDA_ENV,
        "python", "-m", VISION_MODULE,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "vision.log"

    log_file = open(log_path, "a", encoding="utf-8")  # закроем в stop

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._vision_log_file = log_file  # лёгкий хак, чтобы закрыть потом
    return proc

def _stop_proc(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    if getattr(proc, "_vision_log_file", None):
        log_file = proc._vision_log_file

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            proc.kill()

    if getattr(proc, "_vision_log_file", None):
        proc._vision_log_file.close()

def _wait_vision_ready(proc: subprocess.Popen, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None

    while time.time() < deadline:
        # Если процесс умер — сразу падаем и показываем последние строки
        if proc.poll() is not None:
            out = ""
            try:
                if proc.stdout:
                    out = proc.stdout.read()[-2000:]
            except Exception:
                pass
            raise RuntimeError(f"Vision process exited early with code {proc.returncode}. Output tail:\n{out}")

        try:
            r = requests.get(VISION_HEALTH_URL, timeout=0.5)
            if r.status_code == 200:
                return
        except Exception as e:
            last_err = e

        time.sleep(0.25)

    raise TimeoutError(f"Vision service not ready after {timeout_s}s. Last error: {last_err}")

def main() -> None:
    vision_proc = _start_vision()
    try:
        _wait_vision_ready(vision_proc, timeout_s=30.0)

        # Дальше запускаем оркестрацию робота  (py310)
        run_workcell()

    finally:
        _stop_proc(vision_proc)


# def main():
#     run_workcell()

if __name__ == "__main__":
    main()

