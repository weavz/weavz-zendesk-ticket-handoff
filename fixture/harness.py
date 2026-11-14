from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

FIXTURE_PROJECT = Path(__file__).resolve().parent
FIXTURE_SERVER = FIXTURE_PROJECT / "server.py"
FIXTURE_TOKEN = "local-fixture-token"
CODE_EXAMPLE = 'return await weavz.demo.lookup_record({recordId: "record-1"});'
RECORD = {"recordId": "record-1", "title": "Synthetic fixture record", "status": "open"}


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(url: str, process: subprocess.Popen[bytes], timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Fixture server exited early with status {process.returncode}")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # startup race only
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"Fixture server did not become ready: {last_error}")


class FixtureServer:
    def __init__(self, mode: str):
        self.mode = mode
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "FixtureServer":
        env = os.environ.copy()
        env["MCP_TOKEN"] = FIXTURE_TOKEN
        self.process = subprocess.Popen(
            [
                "uv", "run", "--project", str(FIXTURE_PROJECT), "--locked", "python",
                str(FIXTURE_SERVER), "--mode", self.mode, "--port", str(self.port),
            ],
            cwd=FIXTURE_PROJECT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            wait_for_health(self.url.rsplit("/mcp", 1)[0], self.process)
        except BaseException:
            self._stop_process_tree()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self._stop_process_tree()

    def _stop_process_tree(self) -> None:
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=5)
            self.process = None

    def reject_bad_token(self) -> None:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode()
        request = urllib.request.Request(
            self.url, data=body, method="POST", headers={"Authorization": "Bearer wrong-token"}
        )
        try:
            urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise AssertionError(f"Expected 401 for a wrong token, got {exc.code}") from exc
        else:
            raise AssertionError("Fixture accepted a wrong bearer token")


def assert_fixture_result(mode: str, value: Any) -> None:
    serialized = json.dumps(value, default=str)
    if "record-1" not in serialized or "Synthetic fixture record" not in serialized:
        raise AssertionError(f"Unexpected synthetic fixture result: {serialized}")
    if mode not in {"tools", "code"}:
        raise AssertionError(f"Unknown mode {mode!r}")
