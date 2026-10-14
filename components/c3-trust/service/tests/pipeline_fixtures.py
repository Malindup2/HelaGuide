"""Fixtures for tests that run the whole pipeline. Import them into a test module:
        from tests.pipeline_fixtures import ds, pipe, run, settings  # noqa: F401
"""
import pytest

from app.core.evaluate import load_dataset
from app.core.pipeline import Pipeline, set_pipeline
from tests.helpers import make_settings


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def pipe(settings):
    p = Pipeline.build(settings, reset=True)
    p.load_reporters()
    p.sync_facts()
    yield p
    set_pipeline(None)


@pytest.fixture(scope="session")
def ds():
    return load_dataset(make_settings().data_dir)


def run(pipe, ds, message_id):
    """Process one mock message through the right entry point."""
    if message_id in ds.freetext:
        return pipe.process_freetext(ds.freetext[message_id])
    return pipe.process_structured(ds.structured[message_id], ds.extras.get(message_id))
