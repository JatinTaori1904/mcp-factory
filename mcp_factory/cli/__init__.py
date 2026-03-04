"""MCP Factory CLI — Main entry point."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path

from mcp_factory.generator.engine import MCPGenerator
from mcp_factory.storage.db import MCPDatabase
from mcp_factory.validator.checker import MCPValidator
from mcp_factory.generator.api_registry import get_supported_apis
from mcp_factory.llm.interactive import PromptRefiner, is_prompt_vague
from mcp_factory.config import add_server_to_config, remove_server_from_config, export_all_servers, get_claude_config_path, generate_config_snippet

app = typer.Typer(
    name="mcpfactory",
    help="🏭 MCP Factory — Build MCP servers from natural language prompts",
    add_completion=False,
)
console = Console()


@app.command()
def create(
    prompt: str = typer.Argument(..., help="Describe the MCP server you want to build"),
    name: str = typer.Option(None, "--name", "-n", help="Name for the MCP server"),
    language: str = typer.Option("typescript", "--lang", "-l", help="Language: typescript or python"),
    output_dir: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    provider: str = typer.Option("ollama", "--provider", "-p", help="LLM provider: ollama or openai"),
    model: str = typer.Option(None, "--model", "-m", help="Model name (e.g., llama3, gpt-4)"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", "-i", help="Ask follow-up questions for vague prompts"),
):
    """Create a new MCP server from a natural language prompt."""
    console.print(Panel(
        f"[bold blue]🏭 MCP Factory[/bold blue]\n\n"
        f"[dim]Prompt:[/dim] {prompt}\n"
        f"[dim]Language:[/dim] {language}\n"
        f"[dim]Provider:[/dim] {provider}",
        title="Creating MCP Server",
        border_style="blue",
    ))

    # Initialize components
    db = MCPDatabase()
    generator = MCPGenerator(provider=provider, model=model)
    validator = MCPValidator()

    # Show LLM availability
    if generator.llm_available:
        console.print(f"[green]✓[/green] LLM connected: [bold]{generator.model}[/bold] via {provider}")
    else:
        console.print(f"[yellow]⚠[/yellow] LLM not available — using keyword analysis (start Ollama for smart mode)")

    with console.status("[bold green]Analyzing your prompt..."):
        # Step 1: Analyze the prompt to determine template and tools
        analysis = generator.analyze_prompt(prompt)

    # Step 1b: Interactive refinement for vague prompts
    effective_prompt = prompt
    if interactive and is_prompt_vague(prompt):
        refiner = PromptRefiner(llm=generator.llm)
        questions = refiner.generate_questions(prompt, analysis.template, analysis.intent)

        if questions:
            console.print(f"\n[yellow]Your prompt is a bit short.[/yellow] Let me ask a few questions to build a better server:\n")
            answers: dict[str, str] = {}

            for q in questions:
                if q.choices:
                    # Show numbered choices
                    console.print(f"  [bold]{q.question}[/bold]")
                    for idx, choice in enumerate(q.choices, 1):
                        default_marker = " [dim](default)[/dim]" if choice == q.default else ""
                        console.print(f"    [cyan]{idx}.[/cyan] {choice}{default_marker}")
                    raw = typer.prompt("  Enter number or custom answer", default=q.default or q.choices[0])
                    # If user typed a number, map to choice
                    try:
                        choice_idx = int(raw) - 1
                        if 0 <= choice_idx < len(q.choices):
                            answers[q.key] = q.choices[choice_idx]
                        else:
                            answers[q.key] = raw
                    except ValueError:
                        answers[q.key] = raw
                else:
                    answers[q.key] = typer.prompt(f"  {q.question}", default=q.default)
                console.print()

            result_ref = refiner.build_enhanced_prompt(prompt, questions, answers)
            if result_ref.was_refined:
                effective_prompt = result_ref.enhanced_prompt
                console.print(f"[green]✓[/green] Enhanced prompt: [italic]{effective_prompt}[/italic]\n")
                # Re-analyze with enriched prompt
                with console.status("[bold green]Re-analyzing with your details..."):
                    analysis = generator.analyze_prompt(effective_prompt)

    source = analysis.parameters.get("source", "keywords")
    source_label = "[bold green]LLM[/bold green]" if source == "llm" else "[dim]keywords[/dim]"
    console.print(f"\n[green]✓[/green] Analysis source: {source_label}")
    console.print(f"[green]✓[/green] Detected intent: [bold]{analysis.intent}[/bold]")
    console.print(f"[green]✓[/green] Base template: [bold]{analysis.template}[/bold]")
    console.print(f"[green]✓[/green] Tools to generate ({len(analysis.tools)}):")
    for t in analysis.tools:
        mode = "[dim]read-only[/dim]" if t.annotations.read_only else "[yellow]read/write[/yellow]"
        console.print(f"  • [cyan]{t.name}[/cyan] — {t.description[:60]}  {mode}")

    if analysis.api_info:
        api = analysis.api_info
        console.print(f"[green]✓[/green] Detected API: [bold cyan]{api.display_name}[/bold cyan]")
        console.print(f"  [dim]Auth:[/dim] {api.auth_type}  |  [dim]Env var:[/dim] {api.env_var_name}")
        console.print(f"  [dim]Get your key:[/dim] [link={api.key_url}]{api.key_url}[/link]")
        if api.free_tier:
            console.print(f"  [green]✓ Free tier available[/green]")

        # Stage 2: Show tool generation mode
        from mcp_factory.generator.api_tools import has_custom_tools
        if has_custom_tools(api.name):
            console.print(f"  [green]✓ API-specific tools[/green] — Real {api.display_name} endpoints (not generic HTTP)")
        else:
            console.print(f"  [dim]ℹ Using generic HTTP tools — no pre-built {api.display_name} template yet[/dim]")

    with console.status("[bold green]Generating MCP server code..."):
        # Step 2: Generate the MCP server
        server_name = name or analysis.suggested_name
        result = generator.generate(
            analysis=analysis,
            name=server_name,
            language=language,
            output_dir=Path(output_dir),
        )

    if result.success:
        console.print(f"\n[green]✓[/green] Server generated at: [bold]{result.output_path}[/bold]")

        # Step 3: Validate the generated code
        with console.status("[bold green]Validating generated code..."):
            validation = validator.validate(result.output_path, language)

        if validation.is_valid:
            console.print("[green]✓[/green] Validation passed!")
        else:
            console.print("[yellow]⚠[/yellow] Validation warnings:")
            for warning in validation.warnings:
                console.print(f"  [yellow]•[/yellow] {warning}")

        # Step 3b: LLM code review (Stage 3)
        if result.review:
            review = result.review
            # Score color
            if review.score >= 8:
                score_style = "[bold green]"
            elif review.score >= 5:
                score_style = "[bold yellow]"
            else:
                score_style = "[bold red]"

            console.print(f"\n{score_style}Code Review: {review.score}/10[/] — {review.summary}")

            if review.strengths:
                for s in review.strengths[:3]:
                    console.print(f"  [green]✓[/green] {s}")

            if review.issues:
                severity_icons = {"error": "[red]✗[/red]", "warning": "[yellow]![/yellow]", "info": "[dim]ℹ[/dim]"}
                for issue in review.issues[:5]:
                    icon = severity_icons.get(issue.severity, "[dim]•[/dim]")
                    console.print(f"  {icon} [{issue.category}] {issue.message}")
                    if issue.suggestion:
                        console.print(f"    [dim]→ {issue.suggestion}[/dim]")

                if len(review.issues) > 5:
                    console.print(f"  [dim]... and {len(review.issues) - 5} more issues[/dim]")
        else:
            console.print("[dim]ℹ Code review skipped (no LLM available — install Ollama for reviews)[/dim]")

        # Step 4: Save to local database
        db.save_server(
            name=server_name,
            prompt=prompt,
            template=analysis.template,
            language=language,
            output_path=str(result.output_path),
            tools=analysis.tool_names,
        )
        console.print("[green]✓[/green] Server saved to local database")

        # Step 5: Auto-export to Claude Desktop config
        env_vars = None
        if analysis.api_info:
            env_vars = {analysis.api_info.env_var_name: "your-key-here"}
        try:
            config_path, was_added = add_server_to_config(
                name=server_name,
                language=language,
                output_path=str(result.output_path),
                env_vars=env_vars,
            )
            if was_added:
                console.print(f"[green]✓[/green] Added to Claude Desktop config: [dim]{config_path}[/dim]")
        except Exception:
            console.print("[dim]ℹ Could not auto-update Claude Desktop config (use 'mcpfactory config-export' manually)[/dim]")

        # Print next steps
        api_step = ""
        if analysis.api_info:
            api_step = (
                f"\n  [yellow]# Set up your {analysis.api_info.display_name} API key:[/yellow]\n"
                f"  cp .env.example .env\n"
                f"  # Get key at: {analysis.api_info.key_url}\n"
                f"  # See SETUP.md for detailed instructions\n"
            )

        console.print(Panel(
            f"[bold]Next steps:[/bold]\n\n"
            f"  cd {result.output_path}\n"
            f"  {'npm install' if language == 'typescript' else 'pip install -e .'}\n"
            f"{api_step}"
            f"  {'npm start' if language == 'typescript' else 'python -m server'}\n\n"
            f"[green]✓ Claude Desktop config already updated![/green]\n"
            f"[dim]Restart Claude Desktop to load the new server.[/dim]",
            title="🚀 Ready to Run",
            border_style="green",
        ))
    else:
        console.print(f"\n[red]✗[/red] Generation failed: {result.error}")
        raise typer.Exit(1)


@app.command()
def list_servers():
    """List all MCP servers you've created."""
    db = MCPDatabase()
    servers = db.list_servers()

    if not servers:
        console.print("[dim]No servers created yet. Run [bold]mcpfactory create[/bold] to get started![/dim]")
        return

    table = Table(title="🏭 Your MCP Servers")
    table.add_column("Name", style="bold cyan")
    table.add_column("Template", style="green")
    table.add_column("Language", style="yellow")
    table.add_column("Tools", style="dim")
    table.add_column("Created", style="dim")

    for server in servers:
        table.add_row(
            server["name"],
            server["template"],
            server["language"],
            str(server["tool_count"]),
            server["created_at"],
        )

    console.print(table)


@app.command()
def templates():
    """Show available MCP server templates."""
    table = Table(title="📦 Available Templates")
    table.add_column("Template", style="bold cyan")
    table.add_column("Description", style="dim")
    table.add_column("Example Prompt", style="green")

    templates_data = [
        ("file-reader", "Read and process local files", "Read my CSV files and answer questions about the data"),
        ("database-connector", "Connect to SQL databases", "Connect to my PostgreSQL database and run queries"),
        ("api-wrapper", "Wrap REST APIs as MCP tools", "Create tools for the GitHub API"),
        ("web-scraper", "Scrape and extract web data", "Scrape product prices from Amazon"),
        ("document-processor", "Process documents (PDF, DOCX)", "Extract text from PDF invoices and summarize them"),
        ("auth-server", "JWT auth & user management", "Build a login system with JWT tokens and user registration"),
        ("data-pipeline", "ETL data processing", "Create a pipeline to ingest CSV, filter rows, and export results"),
        ("notification-hub", "Multi-channel notifications", "Send notifications via email, webhook, and console log"),
    ]

    for name, desc, example in templates_data:
        table.add_row(name, desc, example)

    console.print(table)


@app.command()
def delete(
    name: str = typer.Argument(..., help="Name of the MCP server to delete"),
    keep_files: bool = typer.Option(False, "--keep-files", help="Keep generated files, only remove from database"),
):
    """Delete an MCP server."""
    db = MCPDatabase()

    if not keep_files:
        server = db.get_server(name)
        if server:
            import shutil
            output_path = Path(server["output_path"])
            if output_path.exists():
                shutil.rmtree(output_path)
                console.print(f"[green]✓[/green] Deleted files at {output_path}")

    db.delete_server(name)
    console.print(f"[green]✓[/green] Server '{name}' removed from database")

    # Also remove from Claude Desktop config
    try:
        removed = remove_server_from_config(name)
        if removed:
            console.print(f"[green]✓[/green] Removed from Claude Desktop config")
    except Exception:
        pass


@app.command()
def info(
    name: str = typer.Argument(..., help="Name of the MCP server"),
):
    """Show detailed info about an MCP server."""
    db = MCPDatabase()
    server = db.get_server(name)

    if not server:
        console.print(f"[red]✗[/red] Server '{name}' not found")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold]Name:[/bold] {server['name']}\n"
        f"[bold]Prompt:[/bold] {server['prompt']}\n"
        f"[bold]Template:[/bold] {server['template']}\n"
        f"[bold]Language:[/bold] {server['language']}\n"
        f"[bold]Path:[/bold] {server['output_path']}\n"
        f"[bold]Tools:[/bold] {', '.join(server['tools'])}\n"
        f"[bold]Created:[/bold] {server['created_at']}",
        title=f"🔍 {server['name']}",
        border_style="blue",
    ))


@app.command()
def supported_apis():
    """Show all APIs with built-in key setup support."""
    apis = get_supported_apis()

    table = Table(title="🔑 Supported APIs (Auto-Detected)")
    table.add_column("API", style="bold cyan")
    table.add_column("Auth Type", style="yellow")
    table.add_column("Env Variable", style="green")
    table.add_column("Free Tier", style="dim")
    table.add_column("Get Key", style="dim")

    for api in apis:
        table.add_row(
            api["display_name"],
            api["auth_type"],
            api["env_var"],
            "✅" if api["free_tier"] else "❌",
            api["key_url"],
        )

    console.print(table)
    console.print(
        "\n[dim]When you mention any of these APIs in your prompt, MCP Factory will "
        "automatically generate API-specific env vars, auth code, and a SETUP.md "
        "with step-by-step key setup instructions.[/dim]"
    )


@app.command(name="config-export")
def config_export(
    output: str = typer.Option(None, "--output", "-o", help="Custom config file path (default: OS-specific Claude Desktop path)"),
):
    """Export all servers to Claude Desktop config (claude_desktop_config.json)."""
    db = MCPDatabase()
    servers_list = db.list_servers()

    if not servers_list:
        console.print("[dim]No servers to export. Run [bold]mcpfactory create[/bold] first.[/dim]")
        return

    # Need full server details (with output_path)
    full_servers = []
    for s in servers_list:
        detail = db.get_server(s["name"])
        if detail:
            full_servers.append(detail)

    config_path = Path(output) if output else None
    path, count = export_all_servers(full_servers, config_path)
    console.print(f"[green]✓[/green] Exported {count} server(s) to [bold]{path}[/bold]")
    console.print("[dim]Restart Claude Desktop to load the changes.[/dim]")


@app.command(name="config-add")
def config_add(
    name: str = typer.Argument(..., help="Name of the MCP server to add to Claude config"),
):
    """Add a single server to Claude Desktop config."""
    db = MCPDatabase()
    server = db.get_server(name)

    if not server:
        console.print(f"[red]✗[/red] Server '{name}' not found. Run [bold]mcpfactory list-servers[/bold] to see available servers.")
        raise typer.Exit(1)

    path, was_added = add_server_to_config(
        name=server["name"],
        language=server["language"],
        output_path=server["output_path"],
    )
    console.print(f"[green]✓[/green] Added '{name}' to Claude Desktop config: [dim]{path}[/dim]")
    console.print("[dim]Restart Claude Desktop to load the changes.[/dim]")


@app.command(name="config-remove")
def config_remove(
    name: str = typer.Argument(..., help="Name of the MCP server to remove from Claude config"),
):
    """Remove a server from Claude Desktop config."""
    removed = remove_server_from_config(name)
    if removed:
        console.print(f"[green]✓[/green] Removed '{name}' from Claude Desktop config")
        console.print("[dim]Restart Claude Desktop to apply the changes.[/dim]")
    else:
        console.print(f"[yellow]⚠[/yellow] Server '{name}' not found in Claude Desktop config")


@app.command(name="config-show")
def config_show():
    """Show the current Claude Desktop config path and contents."""
    path = get_claude_config_path()
    if path.exists():
        import json
        config = json.loads(path.read_text(encoding="utf-8"))
        servers = config.get("mcpServers", {})
        console.print(f"[bold]Config path:[/bold] {path}")
        console.print(f"[bold]MCP servers:[/bold] {len(servers)}\n")

        if servers:
            table = Table(title="Claude Desktop MCP Servers")
            table.add_column("Name", style="bold cyan")
            table.add_column("Command", style="green")
            table.add_column("Args", style="dim")

            for sname, sconfig in servers.items():
                table.add_row(sname, sconfig.get("command", "?"), " ".join(sconfig.get("args", [])))

            console.print(table)
        else:
            console.print("[dim]No MCP servers configured.[/dim]")
    else:
        console.print(f"[dim]Config file not found at {path}[/dim]")
        console.print("[dim]Run [bold]mcpfactory config-export[/bold] to create it.[/dim]")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
):
    """Launch the MCP Factory web dashboard."""
    try:
        from web.app import start_server
    except ImportError:
        console.print("[red]✗ Web dependencies missing.[/red]")
        console.print("Install with: [bold]pip install prompt2mcp\\[web][/bold]")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold blue]🏭 MCP Factory — Web Dashboard[/bold blue]\n\n"
        f"Open [bold cyan]http://{host}:{port}[/bold cyan] in your browser",
        border_style="blue",
    ))
    start_server(host=host, port=port)


if __name__ == "__main__":
    app()
