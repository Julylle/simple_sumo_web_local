"""Keep one local Uvicorn process running until stop.ps1 requests a stop."""
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def claim(lock):
    lock.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def supervise(logs, command, port=8000, initial_delay=5, poll=1):
    logs.mkdir(parents=True, exist_ok=True)
    stop = logs / "backend.stop"
    with (logs / "backend-watchdog.lock").open("a+b") as lock:
        try:
            claim(lock)
        except OSError:
            logging.info("Watchdog already running; duplicate launcher exiting")
            return
        delay = initial_delay
        child = None
        try:
            while not stop.exists():
                # Allow enabling supervision while an existing server is running.
                started = time.monotonic()
                try:
                    if listening(port):
                        time.sleep(poll)
                        continue
                    with (logs / "backend.log").open("ab") as out, (logs / "backend_error.log").open("ab") as err:
                        child = subprocess.Popen(command, cwd=BACKEND, stdout=out, stderr=err)
                    logging.info("Backend launched, PID %d", child.pid)
                    while child.poll() is None and not stop.exists():
                        time.sleep(poll)
                    if stop.exists():
                        break
                    logging.warning("Backend PID %d exited with code %s", child.pid, child.returncode)
                    child = None
                except OSError:
                    logging.exception("Backend launch failed")
                if time.monotonic() - started >= 120:
                    delay = initial_delay
                logging.info("Retrying in %s seconds", delay)
                deadline = time.monotonic() + delay
                while not stop.exists() and time.monotonic() < deadline:
                    time.sleep(min(poll, max(0, deadline - time.monotonic())))
                delay = min(60, 2 * delay)
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait()
            logging.info("Backend watchdog stopped")


if __name__ == "__main__":
    log_dir = BACKEND.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(filename=log_dir / "backend_watchdog.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    supervise(log_dir, [sys.executable, "-X", "faulthandler", "-m", "uvicorn", "main:app",
                        "--host", "127.0.0.1", "--port", "8000", "--workers", "1"])
