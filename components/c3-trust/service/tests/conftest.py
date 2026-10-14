import os

# The stub tests (and CI) expect stub mode. Set it before the app is imported, so a leftover
# STUB_MODE=false in your terminal (from running the real service) cannot break them.
os.environ["STUB_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

from helaguide_common.examples import load_example

from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def example():
    return load_example
