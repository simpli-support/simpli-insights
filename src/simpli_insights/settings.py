"""Application settings loaded from environment variables."""

from simpli_core.connectors.settings import SalesforceSettings
from simpli_core.settings import CustomFieldSettings, SimpliSettings


class Settings(SimpliSettings, SalesforceSettings, CustomFieldSettings):
    app_port: int = 8012
    litellm_model: str = "openrouter/google/gemini-2.5-flash-lite"
    max_clusters: int = 20
    min_cluster_size: int = 3


settings = Settings()
