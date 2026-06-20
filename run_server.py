#!/usr/bin/env python
"""
Entry point for the MCP filesystem server (FastMCP 3.x).

Two faces from one codebase, decided by transport:
  - stdio  -> LOCAL face. All tools, including writes. No auth. (daily desktop path)
  - http   -> REMOTE face. Write tools stripped. WorkOS AuthKit required. (mobile read-only)

Read-only is a property of how the server is launched, not an edit to the code:
the write tools still exist; the public (http) face simply never serves them.

Allowed directories are passed with repeatable --allow-dir (NOT a positional, to avoid
the variadic-positional swallowing later options). The server reads MCP_ALLOWED_DIRS.

Local (desktop):
  uv run run_server.py --allow-dir /path/to/vault --transport stdio

Remote (mobile via Tailscale Funnel):
  uv run run_server.py --allow-dir /path/to/vault --transport http --port 8000 \
    --authkit-domain https://<tenant>.authkit.app \
    --public-base-url https://<machine>.<tailnet>.ts.net
"""

import os
import sys
import typer
from typing import List, Optional
from typing_extensions import Annotated

WRITE_TOOLS = ["write_file", "edit_file", "edit_file_at_line", "create_directory", "move_file"]

app = typer.Typer(name="mcp-filesystem", help="MCP Filesystem Server (FastMCP 3.x)", add_completion=False)


@app.callback(invoke_without_command=True)
def main(
    allow_dir: Annotated[
        Optional[List[str]],
        typer.Option("--allow-dir", "-D", help="Allowed directory (repeatable)"),
    ] = None,
    transport: Annotated[str, typer.Option("--transport", "-t", help="stdio | http")] = "stdio",
    host: Annotated[str, typer.Option("--host", help="Bind host for http (local only)")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port for http")] = 8000,
    authkit_domain: Annotated[
        str, typer.Option("--authkit-domain", envvar="MCP_AUTHKIT_DOMAIN",
                          help="WorkOS AuthKit domain, e.g. https://<tenant>.authkit.app")
    ] = "",
    public_base_url: Annotated[
        str, typer.Option("--public-base-url", envvar="MCP_PUBLIC_BASE_URL",
                          help="Public URL the connector reaches, e.g. https://<host>.ts.net")
    ] = "",
    debug: Annotated[bool, typer.Option("--debug", "-d", help="Debug logging")] = False,
) -> None:
    if allow_dir:
        os.environ["MCP_ALLOWED_DIRS"] = os.pathsep.join(allow_dir)
    if debug:
        os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"

    is_remote = transport.lower() in ("http", "sse", "streamable-http")

    if is_remote:
        if not authkit_domain or not public_base_url:
            print("Remote transport requires --authkit-domain and --public-base-url "
                  "(or MCP_AUTHKIT_DOMAIN / MCP_PUBLIC_BASE_URL).", file=sys.stderr)
            sys.exit(2)
        os.environ["MCP_AUTHKIT_DOMAIN"] = authkit_domain
        os.environ["MCP_PUBLIC_BASE_URL"] = public_base_url

    # Deferred import: instance built AFTER env is set -> auth present only on remote face.
    from mcp_filesystem.server import mcp

    try:
        if is_remote:
            for name in WRITE_TOOLS:
                try:
                    mcp.local_provider.remove_tool(name)
                except Exception:
                    pass  # absent already -> stays absent (fail-safe)
            mcp.run(transport="http", host=host, port=port)
        else:
            mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    app()
