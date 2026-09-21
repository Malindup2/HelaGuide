"""Settings read from the environment. See .env.example at the repository root."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "helaguide"
    log_level: str = "INFO"

    # When true, each service answers with the canned samples in contracts/examples.
    # This is what lets every component be developed before the others exist.
    stub_mode: bool = True
    contracts_dir: Path = _REPO_ROOT / "contracts"

    # Service locations (docker network names by default)
    c1_url: str = "http://c1-intent:8001"
    c2_url: str = "http://c2-knowledge-graph:8002"
    c3_url: str = "http://c3-trust:8003"
    c4_url: str = "http://c4-presentation:8004"

    # Stores
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me-neo4j"
    database_url: str = "postgresql://helaguide:change-me-postgres@postgres:5432/helaguide"

    frontend_origin: str = "http://localhost:5173"


def get_settings(**overrides) -> Settings:
    return Settings(**overrides)
