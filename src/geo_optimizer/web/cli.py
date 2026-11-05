"""
CLI entry point to start the web demo.

Usage:
    geo-web                    # Start on localhost:8000
    geo-web --port 3000        # Custom port
    geo-web --host 0.0.0.0     # Accessible from network
"""

from __future__ import annotations

import click


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to listen on")
@click.option("--port", default=8000, help="Port to listen on")
@click.option("--reload", is_flag=True, help="Auto-reload in development")
def main(host, port, reload):
    """Start the GEOSITION web demo."""
    try:
        import uvicorn
    except ImportError as exc:
        click.echo("uvicorn not installed. Use: pip install geosition[web]", err=True)
        raise SystemExit(1) from exc

    click.echo(f"GEOSITION Web Demo: http://{host}:{port}")
    uvicorn.run(
        "geo_optimizer.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
