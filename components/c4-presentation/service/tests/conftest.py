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
