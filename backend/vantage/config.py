"""Runtime configuration.

Every knob lives here. The previous code read os.getenv at 13 call sites
across 9 modules, several at import time, which made missing keys surface as
runtime AttributeErrors deep inside an agent.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    # Storage
    mongodb_uri: SecretStr = Field(..., alias="MONGODB_URI")
    mongodb_database: str = Field("vantage", alias="MONGODB_DATABASE")

    # SEC requires a real contact address in the User-Agent. The old default
    # was "FinancialAnalystBot research@example.com", a fake address, which
    # violates the fair-access policy and risks an IP block.
    sec_user_agent: str = Field(..., alias="SEC_EDGAR_USER_AGENT")

    # LLM providers
    gemini_api_key: SecretStr | None = Field(None, alias="GEMINI_API_KEY")
    groq_api_key: SecretStr | None = Field(None, alias="GROQ_API_KEY")
    huggingface_api_key: SecretStr | None = Field(None, alias="HUGGINGFACE_API_KEY")

    generation_model: str = Field("gemini-2.5-flash", alias="VANTAGE_GENERATION_MODEL")
    judge_model: str = Field("gemini-2.5-flash", alias="VANTAGE_JUDGE_MODEL")
    # Judging generations from the same family measures self-preference as
    # much as quality, so the second judge is deliberately another vendor.
    cross_judge_model: str = Field("llama-3.3-70b-versatile", alias="VANTAGE_CROSS_JUDGE_MODEL")

    # Retrieval. Sizes are the fastembed on-disk footprint, which matters
    # because Render's free tier caps at 512 MB and the process also holds
    # FastAPI, pandas and numpy.
    #   bge-small-en-v1.5   384d  0.067 GB   (default)
    #   bge-base-en-v1.5    768d  0.21  GB   (A/B candidate, local runs only)
    embedding_model: str = Field("BAAI/bge-small-en-v1.5", alias="VANTAGE_EMBEDDING_MODEL")
    embedding_dim: int = Field(384, alias="VANTAGE_EMBEDDING_DIM")
    #   jina-reranker-v1-turbo-en  0.15 GB   (default, fits free tier)
    #   BAAI/bge-reranker-base     1.04 GB   (does not fit free tier)
    reranker_model: str = Field("jinaai/jina-reranker-v1-turbo-en", alias="VANTAGE_RERANKER_MODEL")
    fastembed_cache_path: str | None = Field(None, alias="FASTEMBED_CACHE_PATH")

    retrieval_candidates: int = Field(100, alias="VANTAGE_RETRIEVAL_CANDIDATES")
    retrieval_top_k: int = Field(8, alias="VANTAGE_RETRIEVAL_TOP_K")
    # Reciprocal rank fusion constant. 60 is the value from the original RRF
    # paper and the usual default.
    rrf_k: int = Field(60, alias="VANTAGE_RRF_K")

    # Attention sources. All optional: the layer degrades to whichever are
    # configured. Reddit is deliberately not load-bearing because self-serve
    # API registration closed in late 2025 and approval can be refused.
    reddit_client_id: SecretStr | None = Field(None, alias="REDDIT_CLIENT_ID")
    reddit_client_secret: SecretStr | None = Field(None, alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field("vantage/0.1", alias="REDDIT_USER_AGENT")
    bluesky_handle: str | None = Field(None, alias="BLUESKY_HANDLE")
    bluesky_app_password: SecretStr | None = Field(None, alias="BLUESKY_APP_PASSWORD")
    gnews_api_key: SecretStr | None = Field(None, alias="GNEWS_API_KEY")
    finnhub_api_key: SecretStr | None = Field(None, alias="FINNHUB_API_KEY")
    marketaux_api_key: SecretStr | None = Field(None, alias="MARKETAUX_API_KEY")

    # Observability
    langfuse_public_key: SecretStr | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # API
    api_key: SecretStr | None = Field(None, alias="VANTAGE_API_KEY")
    cors_origins: str = Field("http://localhost:5173", alias="VANTAGE_CORS_ORIGINS")
    rate_limit: str = Field("60/minute", alias="VANTAGE_RATE_LIMIT")
    max_concurrent_jobs: int = Field(2, alias="VANTAGE_MAX_CONCURRENT_JOBS")

    # Provenance. Stamped onto every finding and telemetry row so eval results
    # can be joined back to the code that produced them.
    git_sha: str = Field("unknown", alias="VANTAGE_GIT_SHA")

    @field_validator("sec_user_agent")
    @classmethod
    def _require_contact_address(cls, v: str) -> str:
        """Fail at startup rather than as a mid-run 403.

        SEC fronts data.sec.gov and www.sec.gov with Akamai bot detection that
        answers "Your Request Originates from an Undeclared Automated Tool".
        Measured behaviour, not documented: `Name you@realdomain.com` passes,
        while `Name/0.1 (you@x.com)` and any noreply domain are rejected.
        efts.sec.gov is more permissive, so a bad value fails on only some
        endpoints, which is worse than failing on all of them.
        """
        problems = []
        if "@" not in v:
            problems.append("must contain a contact email")
        if len(v.split()) < 2:
            problems.append("must be '<name or org> <email>', two parts minimum")
        if "/" in v or "(" in v:
            problems.append("must not use the 'Name/version (email)' form, SEC rejects it")
        for bad in ("example.com", "noreply", "no-reply"):
            if bad in v.lower():
                problems.append(f"must not use a {bad} address, SEC rejects it")
        if problems:
            raise ValueError(
                "SEC_EDGAR_USER_AGENT is invalid: "
                + "; ".join(problems)
                + ". Working example: 'Jane Doe jane@herdomain.com'"
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
