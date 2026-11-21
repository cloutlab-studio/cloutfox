"""The API thread says when it could not bind its port instead of claiming success."""

import socket
import threading

import pytest
from fastapi import FastAPI

from src.api import server as server_mod


def _busy_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s, s.getsockname()[1]


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_port_in_use_is_reported(monkeypatch):
    holder, port = _busy_port()
    try:
        monkeypatch.setattr(server_mod, "API_PORT", port)
        failed = []
        done = threading.Event()

        def on_failed(address):
            failed.append(address)
            done.set()

        api = server_mod.APIServer(FastAPI())
        api.start(on_failed=on_failed)
        assert done.wait(20)
        assert failed == [f"127.0.0.1:{port}"]
        assert not api.is_running
    finally:
        holder.close()


def test_free_port_starts_quietly(monkeypatch):
    holder, port = _busy_port()
    holder.close()
    monkeypatch.setattr(server_mod, "API_PORT", port)
    failed = []
    api = server_mod.APIServer(FastAPI())
    api.start(on_failed=failed.append)
    try:
        for _ in range(200):
            if api._server.started:
                break
            threading.Event().wait(0.05)
        assert api._server.started
        threading.Event().wait(0.2)
        assert failed == []
    finally:
        api.stop()
