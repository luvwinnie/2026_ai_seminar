"""画面のテストの準備。偽の OpenCode・backend（一時 DB）・画面（Vite）をここで起動し、最後に止める。

チャットは LLM を呼ばず、OpenCode の代わり（app/backend/tests/fake_opencode.py）につなぐ。
"""

import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = APP_DIR / "backend"
FRONTEND_DIR = APP_DIR / "frontend"
API_PORT = 8120
WEB_PORT = 5220
LOG_DIR = Path(tempfile.mkdtemp(prefix="defect_e2e_"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(url: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"{url} に接続できません（ログ：{LOG_DIR}）")


class Server:
    def __init__(self, name: str, command: list[str], cwd: Path, ready_url: str, env: dict | None = None):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.ready_url = ready_url
        self.env = {**os.environ, **(env or {})}
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        log = open(LOG_DIR / f"{self.name}.log", "a")
        # 子のプロセスもまとめて止められるよう、別のプロセスグループで起動する
        self.process = subprocess.Popen(
            self.command, cwd=self.cwd, env=self.env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        wait_for(self.ready_url)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=10)


@pytest.fixture(scope="session")
def servers():
    for port in (API_PORT, WEB_PORT):
        if port_in_use(port):
            pytest.exit(f"ポート {port} が使われています。起動中のサーバーを止めてから実行してください。", returncode=1)
    fake_port = free_port()
    fake_opencode = Server(
        "fake_opencode",
        [str(BACKEND_DIR / ".venv/bin/uvicorn"), "tests.fake_opencode:app", "--port", str(fake_port)],
        BACKEND_DIR,
        f"http://localhost:{fake_port}/global/health",
    )
    backend = Server(
        "backend",
        [str(BACKEND_DIR / ".venv/bin/uvicorn"), "main:app", "--port", str(API_PORT)],
        BACKEND_DIR,
        f"http://localhost:{API_PORT}/health",
        env={
            "DB_PATH": str(LOG_DIR / "e2e.db"),
            "OPENCODE_URL": f"http://localhost:{fake_port}",
            "OPENCODE_MODEL": "ollama/gemma4:26b",
        },
    )
    frontend = Server(
        "frontend",
        [str(FRONTEND_DIR / "node_modules/.bin/vite"), "--port", str(WEB_PORT), "--strictPort"],
        FRONTEND_DIR,
        f"http://localhost:{WEB_PORT}/",
        env={"API_TARGET": f"http://localhost:{API_PORT}"},
    )
    fake_opencode.start()
    backend.start()
    frontend.start()
    yield {"backend": backend, "frontend": frontend}
    frontend.stop()
    backend.stop()
    fake_opencode.stop()


@pytest.fixture(scope="session")
def base_url(servers):
    return f"http://localhost:{WEB_PORT}"


@pytest.fixture
def backend(servers) -> Server:
    return servers["backend"]
