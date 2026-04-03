# Simpli Insights

Theme discovery and pattern analysis for customer support cases. Part of the [Simpli Support](https://simpli.support) platform.

## Features

- **Theme discovery** — Discover recurring themes from batches of support cases
- **Emerging topics** — Detect trending or emerging topics by comparing recent cases against a baseline
- **Category suggestions** — Suggest a category taxonomy from support case data
- **Distribution analysis** — Analyse the distribution of cases across existing categories

## Quick start

```bash
cp .env.example .env
pip install -e ".[dev]"
simpli-insights serve
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /usage | LLM usage and cost tracking |
| POST | /api/v1/themes | Discover themes from a batch of support cases |
| POST | /api/v1/emerging | Detect emerging or trending topics in recent cases |
| POST | /api/v1/categories | Suggest a category taxonomy from support cases |
| POST | /api/v1/distribution | Analyse distribution of cases across existing categories |

## Configuration

All settings are loaded from environment variables or `.env` files via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

| Variable | Default | Description |
|----------|---------|-------------|
| APP_HOST | 0.0.0.0 | Server bind address |
| APP_PORT | 8000 | Server port |
| APP_LOG_LEVEL | info | Log level |
| LITELLM_MODEL | openai/gpt-5-mini | LLM model identifier |
| CORS_ORIGINS | * | Allowed CORS origins |
| MAX_CLUSTERS | 20 | Maximum number of theme clusters to generate |
| MIN_CLUSTER_SIZE | 3 | Minimum number of cases required to form a cluster |

## Development

```bash
pytest tests/ -q
ruff check .
ruff format --check .
mypy src/
```

## Docker

```bash
docker build -t simpli-insights .
docker run -p 8000:8000 simpli-insights
```

## License

MIT
