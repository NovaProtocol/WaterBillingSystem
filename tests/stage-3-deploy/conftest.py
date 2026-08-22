import os
import subprocess
import time
import urllib.request

import pytest

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
COMPOSE_FILE = os.path.join(BASE, "compose.yaml")


def _wait_for(url, timeout=120, interval=2):
    for _ in range(timeout // interval):
        try:
            r = urllib.request.urlopen(url, timeout=5)
            return r.status
        except Exception:
            time.sleep(interval)
    return None


@pytest.fixture(scope="session")
def stack():
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"],
        cwd=BASE,
        check=True,
        capture_output=True,
    )
    time.sleep(10)
    yield
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-t", "10"],
        cwd=BASE,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def public(stack):
    status = _wait_for("http://127.0.0.1:7020/health")
    assert status == 200, "Public endpoint not healthy"
    return "http://127.0.0.1:7020"


@pytest.fixture(scope="session")
def private(stack):
    status = _wait_for("http://127.0.0.1:7021/health")
    assert status in (200, 302), "Private endpoint not responding"
    return "http://127.0.0.1:7021"
