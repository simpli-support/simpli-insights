"""Application settings loaded from environment variables."""

from simpli_core.connectors.settings import SalesforceSettings
from simpli_core.settings import SimpliSettings


class Settings(SimpliSettings, SalesforceSettings):
    litellm_model: str = "openai/gpt-5-mini"
    cors_origins: str = "*"
    max_clusters: int = 20
    min_cluster_size: int = 3


settings = Settings()
