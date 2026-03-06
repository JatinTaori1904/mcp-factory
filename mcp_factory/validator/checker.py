"""MCP Validator — Validates generated MCP server code."""

from dataclasses import dataclass, field
from pathlib import Path
import json
import ast


@dataclass
class ValidationResult:
    """Result of validating a generated MCP server."""
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class MCPValidator:
    """Validates generated MCP server code for correctness."""

    def validate(self, server_path: Path, language: str) -> ValidationResult:
        """Validate a generated MCP server."""
        result = ValidationResult()

        if not server_path.exists():
            result.is_valid = False
            result.errors.append(f"Server directory does not exist: {server_path}")
            return result

        if language == "typescript":
            self._validate_typescript(server_path, result)
        elif language == "python":
            self._validate_python(server_path, result)

        return result

    def _validate_typescript(self, server_path: Path, result: ValidationResult):
        """Validate a TypeScript MCP server."""
        # Check package.json exists and is valid
        pkg_path = server_path / "package.json"
        if not pkg_path.exists():
            result.is_valid = False
            result.errors.append("Missing package.json")
        else:
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                if "@modelcontextprotocol/sdk" not in pkg.get("dependencies", {}):
                    result.warnings.append("Missing @modelcontextprotocol/sdk dependency")
            except json.JSONDecodeError:
                result.is_valid = False
                result.errors.append("Invalid package.json")

        # Check main source file exists
        index_path = server_path / "src" / "index.ts"
        if not index_path.exists():
            result.is_valid = False
            result.errors.append("Missing src/index.ts")
        else:
            content = index_path.read_text(encoding="utf-8")
            if "McpServer" not in content and "Server" not in content:
                result.warnings.append("No MCP Server class found in index.ts")
            if "server.tool" not in content:
                result.warnings.append("No tools defined in index.ts")

            # MCP Best practices checks
            if "annotations" not in content:
                result.warnings.append("No tool annotations found — add readOnlyHint/destructiveHint")
            if ".describe(" not in content:
                result.warnings.append("Zod schemas missing .describe() — add descriptions to all fields")
            if "errorResponse" not in content and "isError" not in content:
                result.warnings.append("No actionable error handling pattern found")

        # Check tsconfig exists
        if not (server_path / "tsconfig.json").exists():
            result.warnings.append("Missing tsconfig.json")

        # Check .env.example and SETUP.md (API key guidance)
        self._validate_api_setup(server_path, result)

    def _validate_python(self, server_path: Path, result: ValidationResult):
        """Validate a Python MCP server."""
        # Check server.py exists and is valid Python
        server_py = server_path / "server.py"
        if not server_py.exists():
            result.is_valid = False
            result.errors.append("Missing server.py")
        else:
            content = server_py.read_text(encoding="utf-8")
            # Check Python syntax
            try:
                ast.parse(content)
            except SyntaxError as e:
                result.is_valid = False
                result.errors.append(f"Python syntax error in server.py: {e}")
                return

            if "FastMCP" not in content and "Server" not in content:
                result.warnings.append("No MCP Server class found in server.py")
            if "@mcp.tool" not in content:
                result.warnings.append("No tools defined in server.py")

            # MCP Best practices checks
            if "def _error" not in content and "_error(" not in content:
                result.warnings.append("No actionable error helper found — add _error() pattern")
            if '"""' not in content and "'''" not in content:
                result.warnings.append("Tool functions missing docstrings — add typed docstrings")

        # Check pyproject.toml
        pyproject = server_path / "pyproject.toml"
        if not pyproject.exists():
            result.warnings.append("Missing pyproject.toml")

        # Check .env.example and SETUP.md (API key guidance)
        self._validate_api_setup(server_path, result)

    # ------------------------------------------------------------------
    # Shared: API setup file checks
    # ------------------------------------------------------------------

    def _validate_api_setup(self, server_path: Path, result: ValidationResult):
        """Check for .env.example and SETUP.md if the server uses env vars."""
        env_example = server_path / ".env.example"
        setup_md = server_path / "SETUP.md"

        if not env_example.exists():
            result.warnings.append("Missing .env.example — users won't know which env vars to set")

        if env_example.exists() and not setup_md.exists():
            # If there are env vars but no SETUP.md, warn
            content = env_example.read_text(encoding="utf-8") if env_example.exists() else ""
            if "API" in content.upper() or "TOKEN" in content.upper() or "KEY" in content.upper():
                result.warnings.append(
                    "Missing SETUP.md — add step-by-step API key instructions for users"
                )
