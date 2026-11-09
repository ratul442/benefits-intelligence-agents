"""Application configuration loaded from environment variables.

All values are read from .env (single source of truth).
No model names or tunables are hardcoded here.
"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Foundry project
    foundry_project_endpoint: str = ""

    # Model (required — set via .env locally, injected by platform in hosted)
    azure_ai_model_deployment_name: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = ""
    azure_openai_api_key: str = ""

    # Agent behaviour (defaults for hosted; overridden by .env locally)
    max_concurrent_topics: int = 9
    llm_temperature: float = 0.0
    llm_max_tokens: int = 16384
    llm_seed: int | None = None  # NOT supported by Responses API (400 error); retained for audit/future use
    llm_top_p: float | None = None  # If set, passed to responses.create; None = server default
    llm_reasoning_effort: str = "low"
    catalog_version: str = ""

    # Deployment traceability
    # Note: The platform injects FOUNDRY_AGENT_VERSION (not AGENT_VERSION),
    # and CONTAINER_TAG is passed as an environment_variable in the version body.
    agent_version: str = ""
    container_tag: str = ""
    prompt_version: str = ""

    # Observability
    enable_instrumentation: bool = True
    applicationinsights_connection_string: str = ""

    # Server (defaults for hosted; overridden by .env locally)
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context) -> None:
        """Post-init: resolve agent_version from CONTAINER_TAG or FOUNDRY_AGENT_VERSION."""
        if not self.agent_version:
            # Prefer CONTAINER_TAG (our explicit tag) over FOUNDRY_AGENT_VERSION
            # (platform-injected integer like "1" which isn't useful for traceability)
            self.agent_version = (
                os.environ.get("CONTAINER_TAG", "")
                or os.environ.get("FOUNDRY_AGENT_VERSION", "")
            )
        if not self.prompt_version:
            self.prompt_version = os.environ.get(
                "PROMPT_VERSION", "2026-11-extraction-accuracy-v2"
            )


settings = Settings()
