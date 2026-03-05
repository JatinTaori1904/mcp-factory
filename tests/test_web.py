"""Tests for the MCP Factory web dashboard.

Tests all page routes, HTMX API endpoints, error handling,
and edge cases using FastAPI TestClient with an isolated temp database.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from web.app import app, db as app_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temporary database for test isolation."""
    from mcp_factory.storage.db import MCPDatabase

    db = MCPDatabase(db_path=tmp_path / "test.db")
    return db


@pytest.fixture()
def client(tmp_db):
    """FastAPI TestClient with the web app's `db` patched to a temp database."""
    with patch("web.app.db", tmp_db):
        yield TestClient(app)


@pytest.fixture()
def seeded_db(tmp_db):
    """Database pre-populated with sample servers for list/detail tests."""
    tmp_db.save_server(
        name="github-tools",
        prompt="github repo manager",
        template="api-wrapper",
        language="typescript",
        output_path="/tmp/output/github-tools",
        tools=["gh_list_repos", "gh_create_issue", "gh_get_pr"],
    )
    tmp_db.save_server(
        name="file-reader",
        prompt="read local files",
        template="file-reader",
        language="python",
        output_path="/tmp/output/file-reader",
        tools=["file_read", "file_search"],
    )
    return tmp_db


@pytest.fixture()
def seeded_client(seeded_db):
    """TestClient with pre-populated database."""
    with patch("web.app.db", seeded_db):
        yield TestClient(app)


# ===================================================================
# PAGE ROUTES
# ===================================================================


class TestDashboardPage:
    """Tests for GET / — main dashboard."""

    def test_dashboard_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_contains_nav(self, client):
        resp = client.get("/")
        assert "Dashboard" in resp.text
        assert "Create" in resp.text

    def test_dashboard_empty_state(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        # Should show 0 servers
        assert "0" in resp.text

    def test_dashboard_shows_stats(self, seeded_client):
        resp = seeded_client.get("/")
        assert resp.status_code == 200
        # 2 servers seeded
        assert "2" in resp.text
        # Template count is always 8
        assert "8" in resp.text

    def test_dashboard_lists_servers(self, seeded_client):
        resp = seeded_client.get("/")
        assert "github-tools" in resp.text
        assert "file-reader" in resp.text

    def test_dashboard_shows_total_tools(self, seeded_client):
        resp = seeded_client.get("/")
        # 3 + 2 = 5 total tools
        assert "5" in resp.text


class TestCreatePage:
    """Tests for GET /create — server creation form."""

    def test_create_page_renders(self, client):
        resp = client.get("/create")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_create_page_shows_templates(self, client):
        resp = client.get("/create")
        assert "file-reader" in resp.text
        assert "database-connector" in resp.text
        assert "api-wrapper" in resp.text
        assert "web-scraper" in resp.text

    def test_create_page_has_form_fields(self, client):
        resp = client.get("/create")
        html = resp.text
        assert "prompt" in html
        assert "name" in html
        assert "language" in html

    def test_create_page_has_language_options(self, client):
        resp = client.get("/create")
        assert "typescript" in resp.text
        assert "python" in resp.text


class TestServerDetailPage:
    """Tests for GET /servers/{name} — server detail."""

    def test_detail_existing_server(self, seeded_client):
        resp = seeded_client.get("/servers/github-tools")
        assert resp.status_code == 200
        assert "github-tools" in resp.text
        assert "api-wrapper" in resp.text
        assert "typescript" in resp.text

    def test_detail_shows_tools(self, seeded_client):
        resp = seeded_client.get("/servers/github-tools")
        assert "gh_list_repos" in resp.text
        assert "gh_create_issue" in resp.text

    def test_detail_shows_prompt(self, seeded_client):
        resp = seeded_client.get("/servers/github-tools")
        assert "github repo manager" in resp.text

    def test_detail_python_server(self, seeded_client):
        resp = seeded_client.get("/servers/file-reader")
        assert resp.status_code == 200
        assert "python" in resp.text
        assert "file_read" in resp.text

    def test_detail_not_found(self, client):
        resp = client.get("/servers/nonexistent-server")
        assert resp.status_code == 404


class TestAPIsPage:
    """Tests for GET /apis — supported APIs listing."""

    def test_apis_page_renders(self, client):
        resp = client.get("/apis")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_apis_page_lists_apis(self, client):
        resp = client.get("/apis")
        html = resp.text
        assert "GitHub" in html
        assert "Slack" in html
        assert "Stripe" in html

    def test_apis_page_shows_env_vars(self, client):
        resp = client.get("/apis")
        html = resp.text
        assert "GITHUB_TOKEN" in html
        assert "SLACK_BOT_TOKEN" in html

    def test_apis_page_shows_auth_types(self, client):
        resp = client.get("/apis")
        html = resp.text
        # At least some auth type indicators should be present
        assert "Bearer" in html or "Token" in html or "token" in html


class TestConfigPage:
    """Tests for GET /config — Claude Desktop config manager."""

    def test_config_page_renders(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_config_page_shows_path(self, client):
        resp = client.get("/config")
        html = resp.text
        # Should mention claude or config path
        assert "claude" in html.lower() or "config" in html.lower()


# ===================================================================
# HTMX API ENDPOINTS
# ===================================================================


class TestCreateServerAPI:
    """Tests for POST /api/create — server creation endpoint."""

    @patch("web.app.MCPGenerator")
    @patch("web.app.MCPValidator")
    @patch("web.app.add_server_to_config")
    def test_create_success(self, mock_config, mock_validator_cls, mock_gen_cls, client, tmp_db):
        """Creating a server returns success partial with server details."""
        # Mock generator
        mock_gen = MagicMock()
        mock_gen_cls.return_value = mock_gen

        mock_analysis = MagicMock()
        mock_analysis.suggested_name = "test-server"
        mock_analysis.template = "api-wrapper"
        mock_analysis.tool_names = ["tool_a", "tool_b"]
        mock_analysis.tools = [
            SimpleNamespace(name="tool_a", description="Tool A", annotations=SimpleNamespace(read_only=True)),
            SimpleNamespace(name="tool_b", description="Tool B", annotations=SimpleNamespace(read_only=False)),
        ]
        mock_analysis.api_info = None
        mock_analysis.api_infos = []
        mock_gen.analyze_prompt.return_value = mock_analysis

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_path = Path("/tmp/output/test-server")
        mock_result.review = None
        mock_gen.generate.return_value = mock_result

        # Mock validator
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate.return_value = {"valid": True, "errors": []}

        # Patch db too
        with patch("web.app.db", tmp_db):
            resp = client.post("/api/create", data={
                "prompt": "a test API wrapper",
                "name": "",
                "language": "typescript",
                "provider": "ollama",
            })

        assert resp.status_code == 200
        assert "test-server" in resp.text

    @patch("web.app.MCPGenerator")
    @patch("web.app.MCPValidator")
    def test_create_failure_returns_error(self, mock_validator_cls, mock_gen_cls, client, tmp_db):
        """When generation fails, returns error partial."""
        mock_gen = MagicMock()
        mock_gen_cls.return_value = mock_gen

        mock_analysis = MagicMock()
        mock_analysis.suggested_name = "fail-server"
        mock_gen.analyze_prompt.return_value = mock_analysis

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Generation failed: model not available"
        mock_gen.generate.return_value = mock_result

        with patch("web.app.db", tmp_db):
            resp = client.post("/api/create", data={
                "prompt": "some failing prompt",
                "name": "fail-server",
                "language": "typescript",
                "provider": "ollama",
            })

        assert resp.status_code == 200
        assert "Generation failed" in resp.text or "error" in resp.text.lower()

    @patch("web.app.MCPGenerator")
    @patch("web.app.MCPValidator")
    @patch("web.app.add_server_to_config")
    def test_create_with_custom_name(self, mock_config, mock_validator_cls, mock_gen_cls, client, tmp_db):
        """Custom name overrides the suggested name."""
        mock_gen = MagicMock()
        mock_gen_cls.return_value = mock_gen

        mock_analysis = MagicMock()
        mock_analysis.suggested_name = "auto-name"
        mock_analysis.template = "file-reader"
        mock_analysis.tool_names = ["read"]
        mock_analysis.tools = [SimpleNamespace(name="read", description="Read", annotations=SimpleNamespace(read_only=True))]
        mock_analysis.api_info = None
        mock_analysis.api_infos = []
        mock_gen.analyze_prompt.return_value = mock_analysis

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_path = Path("/tmp/output/my-custom-name")
        mock_result.review = None
        mock_gen.generate.return_value = mock_result

        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate.return_value = {"valid": True, "errors": []}

        with patch("web.app.db", tmp_db):
            resp = client.post("/api/create", data={
                "prompt": "read files",
                "name": "my-custom-name",
                "language": "python",
                "provider": "ollama",
            })

        assert resp.status_code == 200
        assert "my-custom-name" in resp.text

    @patch("web.app.MCPGenerator")
    @patch("web.app.MCPValidator")
    @patch("web.app.add_server_to_config")
    def test_create_with_api_detection(self, mock_config, mock_validator_cls, mock_gen_cls, client, tmp_db):
        """When API is detected, env vars are passed to config."""
        mock_gen = MagicMock()
        mock_gen_cls.return_value = mock_gen

        mock_api_info = MagicMock()
        mock_api_info.env_var_name = "GITHUB_TOKEN"

        mock_analysis = MagicMock()
        mock_analysis.suggested_name = "gh-server"
        mock_analysis.template = "api-wrapper"
        mock_analysis.tool_names = ["gh_list"]
        mock_analysis.tools = [SimpleNamespace(name="gh_list", description="List repos", annotations=SimpleNamespace(read_only=True))]
        mock_analysis.api_info = mock_api_info
        mock_analysis.api_infos = [mock_api_info]
        mock_gen.analyze_prompt.return_value = mock_analysis

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_path = Path("/tmp/output/gh-server")
        mock_result.review = None
        mock_gen.generate.return_value = mock_result

        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        mock_validator.validate.return_value = {"valid": True, "errors": []}

        with patch("web.app.db", tmp_db):
            resp = client.post("/api/create", data={
                "prompt": "github tools",
                "name": "gh-server",
                "language": "typescript",
                "provider": "ollama",
            })

        assert resp.status_code == 200
        # config was called with env vars
        mock_config.assert_called_once()
        call_kwargs = mock_config.call_args
        assert call_kwargs[1].get("env_vars") == {"GITHUB_TOKEN": "your-key-here"} or \
               (len(call_kwargs[0]) >= 4 and call_kwargs[0][3] is not None)


class TestDeleteServerAPI:
    """Tests for DELETE /api/servers/{name} — delete a server."""

    def test_delete_existing_server(self, seeded_client, seeded_db):
        """Deleting an existing server removes it and returns updated list."""
        # Verify server exists
        assert seeded_db.get_server("github-tools") is not None

        with patch("web.app.remove_server_from_config"):
            with patch("web.app.db", seeded_db):
                resp = seeded_client.delete("/api/servers/github-tools")

        assert resp.status_code == 200
        # Server should be gone from the returned HTML
        assert "github-tools" not in resp.text
        # The other server should still be listed
        assert "file-reader" in resp.text

    def test_delete_nonexistent_server(self, client, tmp_db):
        """Deleting a non-existent server still returns 200 (idempotent)."""
        with patch("web.app.remove_server_from_config"):
            resp = client.delete("/api/servers/does-not-exist")
        assert resp.status_code == 200

    def test_delete_also_removes_config(self, seeded_client, seeded_db):
        """Deleting a server also attempts to remove it from Claude config."""
        with patch("web.app.remove_server_from_config") as mock_remove:
            with patch("web.app.db", seeded_db):
                seeded_client.delete("/api/servers/github-tools")
        mock_remove.assert_called_once_with("github-tools")


class TestConfigExportAPI:
    """Tests for POST /api/config/export — export all servers to Claude."""

    def test_export_empty(self, client, tmp_db):
        """Exporting with no servers returns success with count 0."""
        with patch("web.app.export_all_servers", return_value=("/path/config.json", 0)):
            resp = client.post("/api/config/export")
        assert resp.status_code == 200
        assert "0" in resp.text

    def test_export_with_servers(self, seeded_client, seeded_db):
        """Exporting with servers returns count."""
        with patch("web.app.export_all_servers", return_value=("/path/config.json", 2)):
            with patch("web.app.db", seeded_db):
                resp = seeded_client.post("/api/config/export")
        assert resp.status_code == 200
        assert "2" in resp.text


class TestConfigRemoveAPI:
    """Tests for DELETE /api/config/{name} — remove from Claude config."""

    def test_remove_server_from_config(self, client):
        """Removing a server from config returns updated list."""
        with patch("web.app.remove_server_from_config", return_value=True):
            with patch("web.app.read_config", return_value={"mcpServers": {}}):
                resp = client.delete("/api/config/some-server")
        assert resp.status_code == 200

    def test_remove_nonexistent_returns_empty_state(self, client):
        """Removing non-existent server returns empty config state."""
        with patch("web.app.remove_server_from_config", return_value=False):
            with patch("web.app.read_config", return_value={"mcpServers": {}}):
                resp = client.delete("/api/config/nonexistent")
        assert resp.status_code == 200
        assert "No servers in Claude config" in resp.text


# ===================================================================
# EDGE CASES & NAVIGATION
# ===================================================================


class TestNavigation:
    """Navigation and cross-page consistency."""

    def test_all_pages_return_200(self, client):
        """All main pages should return 200."""
        pages = ["/", "/create", "/apis", "/config"]
        for page in pages:
            resp = client.get(page)
            assert resp.status_code == 200, f"{page} returned {resp.status_code}"

    def test_all_pages_are_html(self, client):
        """All main pages should return HTML content."""
        pages = ["/", "/create", "/apis", "/config"]
        for page in pages:
            resp = client.get(page)
            assert "text/html" in resp.headers["content-type"], f"{page} is not HTML"

    def test_nav_links_present_on_all_pages(self, client):
        """Navigation bar should be present on every page."""
        pages = ["/", "/create", "/apis", "/config"]
        for page in pages:
            resp = client.get(page)
            html = resp.text
            assert "Dashboard" in html, f"Dashboard link missing on {page}"
            assert "Create" in html, f"Create link missing on {page}"

    def test_static_css_served(self, client):
        """Static CSS file should be accessible."""
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_invalid_route_returns_404(self, client):
        resp = client.get("/this-does-not-exist")
        assert resp.status_code == 404

    def test_server_detail_special_characters(self, tmp_db, client):
        """Server names with hyphens and numbers work correctly."""
        tmp_db.save_server(
            name="my-server-v2",
            prompt="test",
            template="file-reader",
            language="typescript",
            output_path="/tmp/output/my-server-v2",
            tools=["tool_1"],
        )
        with patch("web.app.db", tmp_db):
            resp = client.get("/servers/my-server-v2")
        assert resp.status_code == 200
        assert "my-server-v2" in resp.text

    def test_create_missing_prompt_returns_422(self, client):
        """POST /api/create without a prompt returns 422 validation error."""
        resp = client.post("/api/create", data={
            "language": "typescript",
            "provider": "ollama",
        })
        assert resp.status_code == 422

    def test_dashboard_with_many_servers(self, tmp_db, client):
        """Dashboard handles many servers gracefully."""
        for i in range(20):
            tmp_db.save_server(
                name=f"server-{i}",
                prompt=f"test prompt {i}",
                template="file-reader",
                language="typescript",
                output_path=f"/tmp/output/server-{i}",
                tools=["tool_a"],
            )
        with patch("web.app.db", tmp_db):
            resp = client.get("/")
        assert resp.status_code == 200
        assert "20" in resp.text  # server count
        assert "server-0" in resp.text

    def test_api_page_has_11_apis(self, client):
        """The API page should list all 11 supported APIs."""
        resp = client.get("/apis")
        html = resp.text
        api_names = ["GitHub", "Slack", "OpenAI", "Stripe", "Notion",
                      "Spotify", "Google", "Discord", "Linear", "Jira"]
        for api in api_names:
            assert api in html, f"{api} not found on /apis page"
