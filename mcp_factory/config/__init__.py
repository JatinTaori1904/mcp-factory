"""MCP Factory — Claude Desktop config exporter.

Auto-generates or updates claude_desktop_config.json so generated MCP servers
can be instantly used with Claude Desktop.
"""

import json
import platform
from pathlib import Path
from typing import Optional


def get_claude_config_path() -> Path:
    """Return the default claude_desktop_config.json path for the current OS."""
    system = platform.system()
    if system == "Windows":
        return Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        # Linux / other
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def build_server_entry(
    name: str,
    language: str,
    output_path: str,
    env_vars: Optional[dict[str, str]] = None,
) -> dict:
    """Build a single MCP server entry for claude_desktop_config.json.

    Args:
        name: Server name (used as the key in mcpServers).
        language: 'typescript' or 'python'.
        output_path: Absolute path to the generated server directory.
        env_vars: Optional dict of environment variables (e.g. {"GITHUB_TOKEN": "your-token"}).

    Returns:
        Dict with 'command', 'args', and optionally 'env'.
    """
    server_path = Path(output_path)

    if language == "typescript":
        entry = {
            "command": "node",
            "args": [str(server_path / "dist" / "index.js")],
        }
    else:
        entry = {
            "command": "python",
            "args": [str(server_path / "server.py")],
        }

    if env_vars:
        entry["env"] = env_vars

    return entry


def read_config(config_path: Optional[Path] = None) -> dict:
    """Read the existing Claude Desktop config, or return a default structure.

    Args:
        config_path: Path to config file. Uses OS default if None.

    Returns:
        Parsed config dict with at least an 'mcpServers' key.
    """
    path = config_path or get_claude_config_path()

    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
            config = json.loads(raw)
            if "mcpServers" not in config:
                config["mcpServers"] = {}
            return config
        except (json.JSONDecodeError, OSError):
            return {"mcpServers": {}}
    else:
        return {"mcpServers": {}}


def write_config(config: dict, config_path: Optional[Path] = None) -> Path:
    """Write the Claude Desktop config JSON file.

    Args:
        config: Full config dict to write.
        config_path: Path to config file. Uses OS default if None.

    Returns:
        Path to the written config file.
    """
    path = config_path or get_claude_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def add_server_to_config(
    name: str,
    language: str,
    output_path: str,
    env_vars: Optional[dict[str, str]] = None,
    config_path: Optional[Path] = None,
    overwrite: bool = True,
) -> tuple[Path, bool]:
    """Add (or update) a server entry in Claude Desktop config.

    Args:
        name: Server name.
        language: 'typescript' or 'python'.
        output_path: Path to the generated server directory.
        env_vars: Optional environment variables.
        config_path: Custom config path (uses OS default if None).
        overwrite: If True, overwrite existing entry with same name.

    Returns:
        Tuple of (config_path, was_added). was_added is False if entry
        already existed and overwrite=False.
    """
    config = read_config(config_path)
    entry = build_server_entry(name, language, output_path, env_vars)

    if name in config["mcpServers"] and not overwrite:
        return (config_path or get_claude_config_path(), False)

    config["mcpServers"][name] = entry
    path = write_config(config, config_path)
    return (path, True)


def remove_server_from_config(
    name: str,
    config_path: Optional[Path] = None,
) -> bool:
    """Remove a server entry from Claude Desktop config.

    Args:
        name: Server name to remove.
        config_path: Custom config path.

    Returns:
        True if the server was found and removed, False if not found.
    """
    config = read_config(config_path)
    if name not in config.get("mcpServers", {}):
        return False

    del config["mcpServers"][name]
    write_config(config, config_path)
    return True


def export_all_servers(
    servers: list[dict],
    config_path: Optional[Path] = None,
) -> tuple[Path, int]:
    """Export all tracked servers to Claude Desktop config.

    Args:
        servers: List of server dicts from MCPDatabase.get_server().
        config_path: Custom config path.

    Returns:
        Tuple of (config_path, count_added).
    """
    config = read_config(config_path)
    count = 0

    for server in servers:
        entry = build_server_entry(
            name=server["name"],
            language=server["language"],
            output_path=server["output_path"],
        )
        config["mcpServers"][server["name"]] = entry
        count += 1

    path = write_config(config, config_path)
    return (path, count)


def generate_config_snippet(
    name: str,
    language: str,
    output_path: str,
    env_vars: Optional[dict[str, str]] = None,
) -> str:
    """Generate a JSON snippet for manual copy-paste (no file write).

    Args:
        name: Server name.
        language: 'typescript' or 'python'.
        output_path: Path to the generated server directory.
        env_vars: Optional environment variables.

    Returns:
        Formatted JSON string of the mcpServers entry.
    """
    entry = build_server_entry(name, language, output_path, env_vars)
    snippet = {"mcpServers": {name: entry}}
    return json.dumps(snippet, indent=2)
