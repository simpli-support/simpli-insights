# Simpli Insights

Theme discovery and pattern analysis for customer support cases.

## Features

- **Theme clustering** -- group support cases into meaningful themes
- **Emerging topic detection** -- spot trending issues before they escalate
- **Category taxonomy** -- suggest and refine category structures from real data
- **Distribution analysis** -- understand how cases spread across categories
- **Model flexibility** -- supports OpenAI, Azure OpenAI, Anthropic, Gemini, OpenRouter, Ollama via litellm

## Quick Start

```bash
pip install -e ".[dev]"
simpli-insights serve
```

## API

- `POST /api/v1/themes` -- discover themes from a batch of cases
- `POST /api/v1/emerging` -- detect emerging/trending topics
- `POST /api/v1/categories` -- suggest category taxonomy
- `POST /api/v1/distribution` -- analyse category distribution
- `GET /health` -- health check
- `GET /usage` -- LLM token usage and cost summary

## Development

```bash
ruff check .
mypy src/
pytest
```
