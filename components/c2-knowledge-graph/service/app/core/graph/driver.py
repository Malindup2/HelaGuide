"""One shared Neo4j driver for the public /v1/* API, built from the service's own
settings (helaguide_common.config), not from .env directly -- that file is for local
tooling (admin_ui.py) run on the host; inside the container the settings' defaults
already point at the docker network."""

from __future__ import annotations

from functools import lru_cache

from neo4j import Driver, GraphDatabase

from helaguide_common.config import get_settings


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
