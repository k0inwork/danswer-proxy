"""
Pytest configuration and shared fixtures for unit and integration testing.
"""

import socket
import threading
import time
import pytest
from werkzeug.serving import make_server

from orchestrator.mock_onyx_server import app as mock_onyx_app, reset_mock_state


def find_free_port():
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__()
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture
def mock_onyx_server():
    """Starts a live background Mock Onyx HTTP server on an open port."""
    reset_mock_state()
    port = find_free_port()
    host = "127.0.0.1"
    server_thread = ServerThread(mock_onyx_app, host, port)
    server_thread.start()

    # Small sleep to ensure server thread started listening
    time.sleep(0.05)

    base_url = f"http://{host}:{port}"
    yield base_url

    server_thread.shutdown()
    server_thread.join()
