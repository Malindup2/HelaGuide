"""
C3 settings and every tunable parameter of the PP1 algorithms, in one place.

Values come from environment variables prefixed C3_ (or from service/.env, which git
ignores). Nothing here depends on another component's configuration.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

C3_ROOT = Path(__file__).resolve().parents[3]            # .../components/c3-trust
DEFAULT_DATA_DIR = C3_ROOT / "research" / "data" / "mock"
DEFAULT_OUT_DIR = C3_ROOT / "research" / "experiments" / "out"


class C3Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="C3_", env_file=".env", extra="ignore")

    # ---- infrastructure ---------------------------------------------------------
    database_url: str = "postgresql://c3:c3pass@localhost:5433/c3_pp1"
    data_dir: Path = DEFAULT_DATA_DIR
    out_dir: Path = DEFAULT_OUT_DIR
    fact_source: Literal["file", "http"] = "file"
    c2_url: str = "http://localhost:8002"
    unverified_hosts: list[str] = []          # hosts C2 reads with relaxed TLS (Algorithm 0a)

    # ---- embedding model --------------------------------------------------------
    embedding_backend: Literal["sbert", "hash"] = "sbert"
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"

    # ---- translation (Gemini) ---------------------------------------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    allow_live_llm: bool = False              # keep False on demo day: the cache is used
    llm_pause_seconds: float = 4.0            # polite gap between calls (free-tier limits)

    # ---- Algorithm 0: initial confidence -----------------------------------------
    c_base: float = 0.90
    phi_unv: float = 0.85
    delta_max: float = 2.0                    # max reputation change per reporter per day
    reward_a: float = 1.0                     # a += reward_a * I when the source confirms a claim
    penalty_b: float = 0.5                    # b += penalty_b when the source contradicts a claim

    # ---- Algorithm G: grounding ---------------------------------------------------
    w_service_cos: float = 0.70
    w_service_alias: float = 0.30
    tau_s: float = 0.40                       # min service score
    delta_s: float = 0.08                     # min lead over the runner-up service
    w_e: float = 0.50                         # embedding similarity
    w_p: float = 0.25                         # predicate agreement
    w_q: float = 0.15                         # qualifier agreement
    w_v: float = 0.10                         # the stored value is mentioned
    tau_f: float = 0.55                       # min fact score
    delta_f: float = 0.08                     # min lead over the runner-up fact
    tau_miss_cos: float = 0.30               # document phrase similarity floor: below it a document is "not in the graph"
    tau_doc_sure: float = 0.60                # at or above this the similarity alone is trusted for a document;
                                              # between tau_miss_cos and this, the message must also share a distinctive word
    tau_f_unique_relief: float = 0.10         # if the service has only ONE fact of the kind discussed, tau_f is lowered by this

    # ---- Algorithm 1: trust (MSRT) ---------------------------------------------------
    w_r: float = 0.40
    w_s: float = 0.25
    w_c: float = 0.20
    w_t: float = 0.15                         # recency
    tau_c: float = 30.0                       # account-age curve, days
    tau_v: float = 14.0                       # visit-recency curve, days
    recency_missing_mode: Literal["neutral", "drop"] = "neutral"
    spec_value: float = 0.30
    spec_when: float = 0.25
    spec_where: float = 0.20
    spec_detail: float = 0.25

    # ---- Algorithm 3a: duplicates ------------------------------------------------------
    tau_dup: float = 0.90
    rho: float = 0.60
    n_supp: int = 2

    # ---- Algorithm 2: confidence (DRCU) ---------------------------------------------------
    theta_esc: float = 0.50                   # below this the fact is flagged
    policy_k: int = 3                         # k credible, independent reports reach theta_esc
    gamma: float = 0.50                       # weight of supporting evidence
    active_cut: float = 0.80                  # conf >= this: status "active"

    # ---- Algorithm 6: warning display -----------------------------------------------------
    n_drops: int = 2                          # confidence-lowering updates before a warning shows
    min_step: float = 0.02                    # a drop smaller than this does not count
    verified_note_days: int = 30

    @property
    def lam(self) -> float:
        """Decay rate derived from the policy (calibration-by-design)."""
        return math.log(self.c_base / self.theta_esc) / self.policy_k


@lru_cache
def get_c3_settings() -> C3Settings:
    return C3Settings()
