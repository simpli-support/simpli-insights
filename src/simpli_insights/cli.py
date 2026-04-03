"""CLI interface."""

import typer
import uvicorn

from simpli_insights import __version__
from simpli_insights.settings import settings

app = typer.Typer(help="Simpli Insights CLI")


@app.command()
def serve(
    host: str = typer.Option(settings.app_host, help="Bind host"),
    port: int = typer.Option(settings.app_port, help="Bind port"),
    reload: bool = typer.Option(settings.app_debug, help="Enable auto-reload"),
) -> None:
    """Start the API server."""
    uvicorn.run(
        "simpli_insights.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.app_log_level,
    )


@app.command()
def version() -> None:
    """Show version."""
    typer.echo(f"simpli-insights {__version__}")
