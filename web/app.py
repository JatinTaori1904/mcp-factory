"""MCP Factory — Web Dashboard (FastAPI + HTMX).

Run with: mcpfactory web
"""

from pathlib import Path

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mcp_factory.generator.engine import MCPGenerator
from mcp_factory.storage.db import MCPDatabase
from mcp_factory.validator.checker import MCPValidator
from mcp_factory.generator.api_registry import get_supported_apis
from mcp_factory.config import (
    add_server_to_config,
    remove_server_from_config,
    export_all_servers,
    get_claude_config_path,
    read_config,
)

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="MCP Factory", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Shared instances
db = MCPDatabase()


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — list all servers."""
    servers = db.list_servers()
    # Compute stats
    total_tools = sum(s.get("tool_count", 0) for s in servers)
    apis = get_supported_apis()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "servers": servers,
        "server_count": len(servers),
        "template_count": 8,
        "api_count": len(apis),
        "total_tools": total_tools,
        "page": "dashboard",
    })


@app.get("/create", response_class=HTMLResponse)
async def create_page(request: Request):
    """Server creation form."""
    templates_data = [
        ("file-reader", "Read and process local files"),
        ("database-connector", "Connect to SQL databases"),
        ("api-wrapper", "Wrap REST APIs as MCP tools"),
        ("web-scraper", "Scrape and extract web data"),
        ("document-processor", "Process documents (PDF, DOCX)"),
        ("auth-server", "JWT auth & user management"),
        ("data-pipeline", "ETL data processing"),
        ("notification-hub", "Multi-channel notifications"),
    ]
    return templates.TemplateResponse("create.html", {
        "request": request,
        "templates": templates_data,
        "page": "create",
    })


@app.get("/servers/{name}", response_class=HTMLResponse)
async def server_detail(request: Request, name: str):
    """Server detail page."""
    server = db.get_server(name)
    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "server": server,
        "page": "servers",
    })


@app.get("/apis", response_class=HTMLResponse)
async def apis_page(request: Request):
    """Supported APIs page."""
    apis = get_supported_apis()
    return templates.TemplateResponse("apis.html", {
        "request": request,
        "apis": apis,
        "page": "apis",
    })


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Claude Desktop config manager."""
    config_path = get_claude_config_path()
    config = read_config()
    mcp_servers = config.get("mcpServers", {})
    return templates.TemplateResponse("config.html", {
        "request": request,
        "config_path": str(config_path),
        "servers": mcp_servers,
        "config_exists": config_path.exists(),
        "page": "config",
    })


# ------------------------------------------------------------------
# HTMX API Endpoints
# ------------------------------------------------------------------


@app.post("/api/create", response_class=HTMLResponse)
async def api_create_server(
    request: Request,
    prompt: str = Form(...),
    name: str = Form(""),
    language: str = Form("typescript"),
    provider: str = Form("ollama"),
):
    """Create a server (HTMX endpoint — returns result partial)."""
    generator = MCPGenerator(provider=provider)
    validator = MCPValidator()

    # Analyze
    analysis = generator.analyze_prompt(prompt)
    server_name = name.strip() or analysis.suggested_name

    # Generate
    result = generator.generate(
        analysis=analysis,
        name=server_name,
        language=language,
        output_dir=Path("./output"),
    )

    if not result.success:
        return templates.TemplateResponse("partials/create_error.html", {
            "request": request,
            "error": result.error,
        })

    # Validate
    validation = validator.validate(result.output_path, language)

    # Save to DB
    db.save_server(
        name=server_name,
        prompt=prompt,
        template=analysis.template,
        language=language,
        output_path=str(result.output_path),
        tools=analysis.tool_names,
    )

    # Auto-add to Claude config
    env_vars = None
    if analysis.api_info:
        env_vars = {analysis.api_info.env_var_name: "your-key-here"}
    try:
        add_server_to_config(
            name=server_name,
            language=language,
            output_path=str(result.output_path),
            env_vars=env_vars,
        )
    except Exception:
        pass

    return templates.TemplateResponse("partials/create_success.html", {
        "request": request,
        "server_name": server_name,
        "template": analysis.template,
        "language": language,
        "tool_count": len(analysis.tools),
        "tools": analysis.tools,
        "output_path": str(result.output_path),
        "validation": validation,
        "review": result.review,
        "api_info": analysis.api_info,
    })


@app.delete("/api/servers/{name}", response_class=HTMLResponse)
async def api_delete_server(request: Request, name: str):
    """Delete a server (HTMX endpoint)."""
    server = db.get_server(name)
    if server:
        import shutil
        output_path = Path(server["output_path"])
        if output_path.exists():
            shutil.rmtree(output_path)

    db.delete_server(name)
    try:
        remove_server_from_config(name)
    except Exception:
        pass

    # Return updated server list
    servers = db.list_servers()
    return templates.TemplateResponse("partials/server_list.html", {
        "request": request,
        "servers": servers,
    })


@app.post("/api/config/export", response_class=HTMLResponse)
async def api_config_export(request: Request):
    """Export all servers to Claude config (HTMX endpoint)."""
    servers_list = db.list_servers()
    full_servers = []
    for s in servers_list:
        detail = db.get_server(s["name"])
        if detail:
            full_servers.append(detail)

    path, count = export_all_servers(full_servers)
    return templates.TemplateResponse("partials/config_status.html", {
        "request": request,
        "message": f"Exported {count} server(s) to {path}",
        "success": True,
    })


@app.delete("/api/config/{name}", response_class=HTMLResponse)
async def api_config_remove(request: Request, name: str):
    """Remove a server from Claude config (HTMX endpoint)."""
    removed = remove_server_from_config(name)
    config = read_config()
    mcp_servers = config.get("mcpServers", {})
    return templates.TemplateResponse("partials/config_list.html", {
        "request": request,
        "servers": mcp_servers,
        "message": f"Removed '{name}'" if removed else f"'{name}' not found",
    })


# ------------------------------------------------------------------
# Run helper
# ------------------------------------------------------------------


def start_server(host: str = "127.0.0.1", port: int = 8000):
    """Start the web dashboard server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
