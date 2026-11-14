"""Exercise restart and deliberate shutdown with real child processes and sockets."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

BACKEND = Path(__file__).resolve().parents[1]
CHILD = """
import http.server, os, sys
from pathlib import Path
server = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), http.server.SimpleHTTPRequestHandler)
with Path(sys.argv[2]).open('a') as f:
    print(os.getpid(), file=f)
server.serve_forever()
"""


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError("Timed out waiting for watchdog")


class WatchdogTests(unittest.TestCase):
    def test_restart_duplicate_launch_and_manual_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            logs = Path(folder)
            pids = logs / 'children'
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            env = dict(os.environ, PYTHONPATH=str(BACKEND))
            argv = [sys.executable, '-c',
                    'import sys; from pathlib import Path; from scripts.backend_watchdog import supervise; '
                    'supervise(Path(sys.argv[1]), sys.argv[3:], int(sys.argv[2]), initial_delay=.1, poll=.05)',
                    str(logs), str(port), sys.executable, '-c', CHILD, str(port), str(pids)]
            watch = subprocess.Popen(argv, env=env)
            try:
                wait_for(lambda: pids.exists() and pids.read_text().strip())
                first = int(pids.read_text().strip())
                # A repeated launch leaves the first watchdog in control.
                subprocess.run(argv, env=env, check=True, timeout=3)
                import signal
                os.kill(first, signal.SIGTERM)
                wait_for(lambda: len(pids.read_text().splitlines()) == 2)
                with urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
                    self.assertEqual(response.status, 200)
                (logs / 'backend.stop').touch()
                self.assertEqual(watch.wait(timeout=5), 0)
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(('127.0.0.1', port)), 0)
            finally:
                (logs / 'backend.stop').touch()
                watch.wait(timeout=5)
