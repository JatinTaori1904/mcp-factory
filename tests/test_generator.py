"""Tests for MCP Generator Engine."""

import pytest
from pathlib import Path
from mcp_factory.generator.engine import MCPGenerator, PromptAnalysis, ToolDefinition, ToolAnnotations
from mcp_factory.llm.client import LLMClient
from mcp_factory.llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, parse_analysis_response


class TestPromptAnalysis:
    """Test prompt analysis and template matching."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_file_reader_detection(self):
        analysis = self.generator.analyze_prompt("Read my CSV files and answer questions")
        assert analysis.template == "file-reader"
        assert "file_read" in analysis.tool_names

    def test_database_detection(self):
        analysis = self.generator.analyze_prompt("Connect to my PostgreSQL database")
        assert analysis.template == "database-connector"
        assert "db_query" in analysis.tool_names

    def test_api_detection(self):
        analysis = self.generator.analyze_prompt("Create tools for the GitHub API endpoints")
        assert analysis.template == "api-wrapper"
        # Stage 2: GitHub gets API-specific tools, not generic api_get
        assert "gh_list_repos" in analysis.tool_names

    def test_web_scraper_detection(self):
        analysis = self.generator.analyze_prompt("Scrape product prices from websites")
        assert analysis.template == "web-scraper"
        assert "scrape_page" in analysis.tool_names

    def test_document_processor_detection(self):
        analysis = self.generator.analyze_prompt("Extract text from PDF invoices and classify documents")
        assert analysis.template == "document-processor"
        assert "doc_extract_text" in analysis.tool_names

    def test_fallback_to_file_reader(self):
        analysis = self.generator.analyze_prompt("do something random for me")
        assert analysis.template == "file-reader"  # default fallback

    def test_suggested_name_generation(self):
        analysis = self.generator.analyze_prompt("Read my CSV files")
        assert analysis.suggested_name != ""
        assert len(analysis.suggested_name) <= 30

    def test_tools_are_tool_definitions(self):
        analysis = self.generator.analyze_prompt("Read my CSV files")
        assert all(isinstance(t, ToolDefinition) for t in analysis.tools)
        assert analysis.tools[0].annotations is not None

    def test_prefix_set(self):
        analysis = self.generator.analyze_prompt("Read my CSV files")
        assert analysis.prefix == "file_"


class TestCodeGeneration:
    """Test MCP server code generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_generate_typescript_server(self, tmp_path):
        tools = [
            ToolDefinition("file_read", "Read a file", ToolAnnotations(read_only=True), "file_"),
            ToolDefinition("file_list", "List files", ToolAnnotations(read_only=True), "file_"),
        ]
        analysis = PromptAnalysis(
            intent="File processing",
            template="file-reader",
            tools=tools,
            tool_names=["file_read", "file_list"],
            suggested_name="test-server",
            prefix="file_",
        )
        result = self.generator.generate(analysis, "test-server", "typescript", tmp_path)
        assert result.success
        assert (result.output_path / "package.json").exists()
        assert (result.output_path / "src" / "index.ts").exists()
        assert (result.output_path / "README.md").exists()
        assert (result.output_path / ".env.example").exists()
        assert (result.output_path / ".gitignore").exists()

        # Verify best practices in generated code
        content = (result.output_path / "src" / "index.ts").read_text()
        assert "annotations" in content, "Tool annotations should be present"
        assert ".describe(" in content, "Zod .describe() should be present"
        assert "errorResponse" in content, "Error helper should be present"

    def test_generate_python_server(self, tmp_path):
        tools = [
            ToolDefinition("file_read", "Read a file", ToolAnnotations(read_only=True), "file_"),
            ToolDefinition("file_list", "List files", ToolAnnotations(read_only=True), "file_"),
        ]
        analysis = PromptAnalysis(
            intent="File processing",
            template="file-reader",
            tools=tools,
            tool_names=["file_read", "file_list"],
            suggested_name="test-server",
            prefix="file_",
        )
        result = self.generator.generate(analysis, "test-server", "python", tmp_path)
        assert result.success
        assert (result.output_path / "server.py").exists()
        assert (result.output_path / "pyproject.toml").exists()
        assert (result.output_path / "README.md").exists()

        # Verify best practices in generated code
        content = (result.output_path / "server.py").read_text()
        assert "@mcp.tool" in content, "FastMCP tools should be present"
        assert "_error(" in content, "Error helper should be present"

    def test_generate_unsupported_language(self, tmp_path):
        analysis = PromptAnalysis(
            intent="test", template="file-reader", tools=[], tool_names=[], suggested_name="test"
        )
        result = self.generator.generate(analysis, "test", "rust", tmp_path)
        assert not result.success
        assert "Unsupported language" in result.error


class TestDockerGeneration:
    """Test Dockerfile and .dockerignore generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def _make_analysis(self, template="file-reader"):
        return PromptAnalysis(
            intent="Test server",
            template=template,
            tools=[
                ToolDefinition("test_read", "Read", ToolAnnotations(read_only=True), "test_"),
            ],
            tool_names=["test_read"],
            suggested_name="test-docker",
            prefix="test_",
        )

    def test_typescript_generates_dockerfile(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "typescript", tmp_path)
        assert result.success
        assert (result.output_path / "Dockerfile").exists()
        assert (result.output_path / ".dockerignore").exists()
        assert "Dockerfile" in result.files_created
        assert ".dockerignore" in result.files_created

    def test_python_generates_dockerfile(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "python", tmp_path)
        assert result.success
        assert (result.output_path / "Dockerfile").exists()
        assert (result.output_path / ".dockerignore").exists()

    def test_ts_dockerfile_content(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "typescript", tmp_path)
        content = (result.output_path / "Dockerfile").read_text()
        assert "FROM node:20-alpine" in content
        assert "npm ci" in content
        assert "npm run build" in content
        assert "ENTRYPOINT" in content
        assert "test-docker" in content

    def test_py_dockerfile_content(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "python", tmp_path)
        content = (result.output_path / "Dockerfile").read_text()
        assert "FROM python:3.12-slim" in content
        assert "pip install" in content
        assert "server.py" in content
        assert "ENTRYPOINT" in content
        assert "test-docker" in content

    def test_ts_dockerfile_has_multistage_build(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "typescript", tmp_path)
        content = (result.output_path / "Dockerfile").read_text()
        assert content.count("FROM ") == 2, "TypeScript should use multi-stage build"
        assert "AS builder" in content

    def test_dockerfile_has_build_instructions(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "typescript", tmp_path)
        content = (result.output_path / "Dockerfile").read_text()
        assert "docker build" in content
        assert "docker run" in content

    def test_dockerignore_excludes_env(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "typescript", tmp_path)
        content = (result.output_path / ".dockerignore").read_text()
        assert ".env" in content
        assert "node_modules" in content

    def test_py_dockerignore_excludes_pycache(self, tmp_path):
        result = self.generator.generate(self._make_analysis(), "test-docker", "python", tmp_path)
        content = (result.output_path / ".dockerignore").read_text()
        assert ".env" in content
        assert "__pycache__" in content

    def test_dockerfile_has_template_label(self, tmp_path):
        analysis = self._make_analysis(template="api-wrapper")
        result = self.generator.generate(analysis, "test-docker", "typescript", tmp_path)
        content = (result.output_path / "Dockerfile").read_text()
        assert "api-wrapper" in content


class TestDatabaseStorage:
    """Test local SQLite storage."""

    def test_save_and_retrieve_server(self, tmp_path):
        from mcp_factory.storage.db import MCPDatabase
        db = MCPDatabase(db_path=tmp_path / "test.db")

        db.save_server(
            name="test-server",
            prompt="Read my files",
            template="file-reader",
            language="python",
            output_path="/tmp/test-server",
            tools=["file_read", "file_list"],
        )

        server = db.get_server("test-server")
        assert server is not None
        assert server["name"] == "test-server"
        assert server["template"] == "file-reader"
        assert "file_read" in server["tools"]

    def test_list_servers(self, tmp_path):
        from mcp_factory.storage.db import MCPDatabase
        db = MCPDatabase(db_path=tmp_path / "test.db")

        db.save_server("s1", "prompt1", "file-reader", "python", "/tmp/s1", ["file_read"])
        db.save_server("s2", "prompt2", "api-wrapper", "typescript", "/tmp/s2", ["api_get"])

        servers = db.list_servers()
        assert len(servers) == 2

    def test_delete_server(self, tmp_path):
        from mcp_factory.storage.db import MCPDatabase
        db = MCPDatabase(db_path=tmp_path / "test.db")

        db.save_server("delete-me", "prompt", "file-reader", "python", "/tmp/x", ["file_read"])
        assert db.server_exists("delete-me")

        db.delete_server("delete-me")
        assert not db.server_exists("delete-me")


class TestAPIRegistry:
    """Test API detection and registry features."""

    def test_detect_github(self):
        from mcp_factory.generator.api_registry import detect_api
        api = detect_api("Create tools for the GitHub API")
        assert api is not None
        assert api.name == "github"
        assert api.env_var_name == "GITHUB_TOKEN"

    def test_detect_slack(self):
        from mcp_factory.generator.api_registry import detect_api
        api = detect_api("Build a Slack bot that posts messages")
        assert api is not None
        assert api.name == "slack"

    def test_detect_stripe(self):
        from mcp_factory.generator.api_registry import detect_api
        api = detect_api("Create a Stripe payment tool")
        assert api is not None
        assert api.name == "stripe"
        assert api.env_var_name == "STRIPE_SECRET_KEY"

    def test_detect_via_keyword(self):
        from mcp_factory.generator.api_registry import detect_api
        api = detect_api("Manage pull requests and issues")
        assert api is not None
        assert api.name == "github"

    def test_detect_none_for_generic(self):
        from mcp_factory.generator.api_registry import detect_api
        api = detect_api("Read my local CSV files")
        assert api is None

    def test_env_file_generation(self):
        from mcp_factory.generator.api_registry import detect_api, generate_env_file
        api = detect_api("Build GitHub API tools")
        assert api is not None
        env = generate_env_file(api)
        assert "GITHUB_TOKEN" in env
        assert api.key_url in env

    def test_setup_guide_generation(self):
        from mcp_factory.generator.api_registry import detect_api, generate_setup_guide
        api = detect_api("Build GitHub API tools")
        assert api is not None
        guide = generate_setup_guide(api, "github-tools", "typescript")
        assert "SETUP.md" not in guide or "github-tools" in guide
        assert api.key_url in guide
        assert "npm install" in guide

    def test_setup_guide_python(self):
        from mcp_factory.generator.api_registry import detect_api, generate_setup_guide
        api = detect_api("Slack bot")
        assert api is not None
        guide = generate_setup_guide(api, "slack-bot", "python")
        assert "pip install" in guide

    def test_get_supported_apis(self):
        from mcp_factory.generator.api_registry import get_supported_apis
        apis = get_supported_apis()
        assert len(apis) == 12
        names = [a["name"] for a in apis]
        assert "github" in names
        assert "slack" in names
        assert "stripe" in names
        # Check structure includes needed fields
        first = apis[0]
        assert "display_name" in first
        assert "auth_type" in first
        assert "free_tier" in first

    def test_analysis_includes_api_info(self):
        generator = MCPGenerator(provider="ollama")
        analysis = generator.analyze_prompt("Create tools for the GitHub API")
        assert analysis.api_info is not None
        assert analysis.api_info.name == "github"
        assert analysis.template == "api-wrapper"

    def test_generated_ts_has_auth(self, tmp_path):
        generator = MCPGenerator(provider="ollama")
        analysis = generator.analyze_prompt("Build GitHub API tools for listing repos")
        result = generator.generate(analysis, "github-tools", "typescript", tmp_path)
        assert result.success

        # Check auth code in generated index.ts
        content = (result.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "GITHUB_TOKEN" in content

        # Check SETUP.md was generated
        assert (result.output_path / "SETUP.md").exists()
        setup = (result.output_path / "SETUP.md").read_text(encoding="utf-8")
        assert "github" in setup.lower()

        # Check .env.example has specific var
        env = (result.output_path / ".env.example").read_text(encoding="utf-8")
        assert "GITHUB_TOKEN" in env

    def test_generated_py_has_auth(self, tmp_path):
        generator = MCPGenerator(provider="ollama")
        analysis = generator.analyze_prompt("Build Slack API tools")
        result = generator.generate(analysis, "slack-tools", "python", tmp_path)
        assert result.success

        content = (result.output_path / "server.py").read_text(encoding="utf-8")
        assert "SLACK_BOT_TOKEN" in content
        assert (result.output_path / "SETUP.md").exists()


class TestLLMClient:
    """Test LLM client and structured prompts."""

    def test_client_creation(self):
        c = LLMClient(provider="ollama", model="llama3")
        assert c.provider == "ollama"
        assert c.model == "llama3"

    def test_default_models(self):
        assert LLMClient(provider="ollama").model == "llama3"
        assert LLMClient(provider="openai").model == "gpt-4o-mini"
        assert LLMClient(provider="claude").model == "claude-sonnet-4-20250514"

    def test_json_extraction_direct(self):
        assert LLMClient._extract_json('{"a": 1}') == {"a": 1}

    def test_json_extraction_code_block(self):
        text = 'Here:\n```json\n{"a": 2}\n```\nDone.'
        assert LLMClient._extract_json(text) == {"a": 2}

    def test_json_extraction_embedded(self):
        text = 'Some text {"a": 3} more text'
        assert LLMClient._extract_json(text) == {"a": 3}

    def test_json_extraction_no_json(self):
        assert LLMClient._extract_json("no json here") is None

    def test_unavailable_provider_returns_error(self):
        c = LLMClient(provider="nonexistent")
        resp = c.chat("system", "user")
        assert not resp.success
        assert resp.error is not None

    def test_reset_clears_cache(self):
        c = LLMClient(provider="ollama")
        _ = c.is_available()
        c.reset()
        assert c._available is None


class TestPromptParser:
    """Test LLM response parsing and validation."""

    def test_valid_response(self):
        data = {
            "intent": "List GitHub repos",
            "template": "api-wrapper",
            "api_name": "github",
            "prefix": "gh_",
            "suggested_name": "github-tools",
            "tools": [
                {"name": "gh_list_repos", "description": "List repos", "read_only": True, "destructive": False, "idempotent": True, "open_world": True},
            ],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["template"] == "api-wrapper"
        assert result["api_names"] == ["github"]
        assert len(result["tools"]) == 1
        assert result["tools"][0]["name"] == "gh_list_repos"

    def test_invalid_template_rejected(self):
        data = {"intent": "test", "template": "magic-template", "tools": [{"name": "t", "description": "d"}]}
        assert parse_analysis_response(data) is None

    def test_missing_fields_rejected(self):
        assert parse_analysis_response({"intent": "test"}) is None
        assert parse_analysis_response({}) is None
        assert parse_analysis_response({"intent": "t", "template": "file-reader"}) is None

    def test_empty_tools_rejected(self):
        data = {"intent": "test", "template": "file-reader", "tools": []}
        assert parse_analysis_response(data) is None

    def test_null_api_normalized(self):
        data = {
            "intent": "Read files",
            "template": "file-reader",
            "api_name": "null",
            "prefix": "file_",
            "tools": [{"name": "file_read", "description": "Read a file", "read_only": True}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["api_names"] == []

    def test_unknown_api_normalized(self):
        data = {
            "intent": "test",
            "template": "api-wrapper",
            "api_name": "some-unknown-api",
            "prefix": "x_",
            "tools": [{"name": "x_get", "description": "Get"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["api_names"] == []

    def test_prefix_inferred_from_tool_name(self):
        data = {
            "intent": "test",
            "template": "api-wrapper",
            "tools": [{"name": "gh_list_repos", "description": "List repos"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["prefix"] == "gh_"

    def test_suggested_name_capped_at_30(self):
        data = {
            "intent": "test",
            "template": "file-reader",
            "suggested_name": "a" * 50,
            "tools": [{"name": "read", "description": "Read"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert len(result["suggested_name"]) <= 30


class TestStage2APISpecificTools:
    """Test Stage 2: API-specific tool generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    # ---- Tool definition tests ----

    def test_github_gets_specific_tools(self):
        a = self.generator.analyze_prompt("Build GitHub API tools")
        assert a.template == "api-wrapper"
        assert a.api_info is not None
        assert a.api_info.name == "github"
        # Should have GitHub-specific tools, not generic ones
        assert "gh_list_repos" in a.tool_names
        assert "gh_create_issue" in a.tool_names
        assert "api_get" not in a.tool_names

    def test_slack_gets_specific_tools(self):
        a = self.generator.analyze_prompt("Create a Slack bot")
        assert a.api_info.name == "slack"
        assert "slack_list_channels" in a.tool_names
        assert "slack_send_message" in a.tool_names
        assert "api_get" not in a.tool_names

    def test_stripe_gets_specific_tools(self):
        a = self.generator.analyze_prompt("Stripe payment integration")
        assert a.api_info.name == "stripe"
        assert "stripe_list_customers" in a.tool_names
        assert "api_get" not in a.tool_names

    def test_notion_gets_specific_tools(self):
        a = self.generator.analyze_prompt("Build a Notion workspace tool")
        assert a.api_info.name == "notion"
        assert "notion_search" in a.tool_names
        assert "notion_create_page" in a.tool_names

    def test_discord_gets_specific_tools(self):
        a = self.generator.analyze_prompt("Discord bot for managing servers")
        assert a.api_info.name == "discord"
        assert "discord_list_guilds" in a.tool_names
        assert "discord_send_message" in a.tool_names

    def test_unknown_api_falls_back_to_generic(self):
        """APIs without pre-built templates (e.g., Spotify) should get generic tools."""
        a = self.generator.analyze_prompt("Build Spotify playlist API tools")
        assert a.api_info is not None
        assert a.api_info.name == "spotify"
        # Spotify doesn't have custom tools, falls back to generic
        assert "api_get" in a.tool_names

    # ---- Code generation tests ----

    def test_github_ts_generates_real_endpoints(self, tmp_path):
        a = self.generator.analyze_prompt("Build GitHub API tools")
        r = self.generator.generate(a, "github-server", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        # Should have real GitHub endpoints, not generic api_get
        assert "gh_list_repos" in content
        assert "gh_create_issue" in content
        assert "/users/" in content or "/repos/" in content
        assert "GITHUB_TOKEN" in content

    def test_github_py_generates_real_endpoints(self, tmp_path):
        a = self.generator.analyze_prompt("Build GitHub API tools")
        r = self.generator.generate(a, "github-server", "python", tmp_path)
        assert r.success
        content = (r.output_path / "server.py").read_text(encoding="utf-8")
        assert "gh_list_repos" in content
        assert "gh_create_issue" in content
        assert "httpx" in content
        assert "GITHUB_TOKEN" in content

    def test_slack_ts_generates_real_endpoints(self, tmp_path):
        a = self.generator.analyze_prompt("Create a Slack bot")
        r = self.generator.generate(a, "slack-bot", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "slack_send_message" in content
        assert "chat.postMessage" in content
        assert "SLACK_BOT_TOKEN" in content

    def test_stripe_py_generates_real_endpoints(self, tmp_path):
        a = self.generator.analyze_prompt("Stripe payment tools")
        r = self.generator.generate(a, "stripe-tools", "python", tmp_path)
        assert r.success
        content = (r.output_path / "server.py").read_text(encoding="utf-8")
        assert "stripe_list_customers" in content
        assert "stripe_create_customer" in content
        assert "/customers" in content

    def test_generic_api_still_works(self, tmp_path):
        """APIs without pre-built templates should still get working generic tools."""
        a = self.generator.analyze_prompt("Build Spotify API tools")
        r = self.generator.generate(a, "spotify-tools", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "api_get" in content
        assert "api_post" in content

    # ---- API tools module tests ----

    def test_has_custom_tools_known(self):
        from mcp_factory.generator.api_tools import has_custom_tools
        assert has_custom_tools("github")
        assert has_custom_tools("slack")
        assert has_custom_tools("stripe")
        assert has_custom_tools("notion")
        assert has_custom_tools("discord")

    def test_has_custom_tools_unknown(self):
        from mcp_factory.generator.api_tools import has_custom_tools
        assert not has_custom_tools("spotify")
        assert not has_custom_tools("twitter")
        assert not has_custom_tools("nonexistent")

    def test_custom_tool_defs_structure(self):
        from mcp_factory.generator.api_tools import get_custom_tool_defs
        defs = get_custom_tool_defs("github")
        assert len(defs) == 5
        names = [d["name"] for d in defs]
        assert "gh_list_repos" in names
        assert "gh_create_issue" in names
        for d in defs:
            assert "description" in d
            assert "read_only" in d

    def test_tool_logic_prompt_builder(self):
        from mcp_factory.llm.prompts import build_tool_logic_prompt
        prompt = build_tool_logic_prompt(
            language="typescript",
            intent="List GitHub repos",
            api_name="github",
            base_url="https://api.github.com",
            tools=[{"name": "gh_list_repos", "description": "List repos", "read_only": True, "destructive": False}],
        )
        assert "typescript" in prompt
        assert "github" in prompt
        assert "gh_list_repos" in prompt


class TestMultiAPISupport:
    """Test multi-API server composition — generating a single server with multiple APIs."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama", model="nonexistent-model-xyz")

    # ---- Detection ----

    def test_detect_multiple_apis_from_prompt(self):
        """detect_apis should find all mentioned APIs in a prompt."""
        from mcp_factory.generator.api_registry import detect_apis
        apis = detect_apis("Build a server that uses GitHub and Slack")
        names = [a.name for a in apis]
        assert "github" in names
        assert "slack" in names
        assert len(apis) >= 2

    def test_detect_three_apis(self):
        from mcp_factory.generator.api_registry import detect_apis
        apis = detect_apis("Integrate GitHub, Slack, and Stripe")
        names = [a.name for a in apis]
        assert "github" in names
        assert "slack" in names
        assert "stripe" in names

    def test_detect_single_api_still_works(self):
        from mcp_factory.generator.api_registry import detect_apis
        apis = detect_apis("Build GitHub tools")
        assert len(apis) == 1
        assert apis[0].name == "github"

    def test_detect_no_api(self):
        from mcp_factory.generator.api_registry import detect_apis
        apis = detect_apis("Read my local CSV files")
        assert apis == []

    # ---- Analysis ----

    def test_analyze_multi_api_prompt(self):
        a = self.generator.analyze_prompt("Build a server with GitHub and Slack integration")
        assert a.template == "api-wrapper"
        assert len(a.api_infos) >= 2
        api_names = [api.name for api in a.api_infos]
        assert "github" in api_names
        assert "slack" in api_names

    def test_api_info_backward_compat(self):
        """api_info property should return first API for backward compat."""
        a = self.generator.analyze_prompt("GitHub and Slack tools")
        assert a.api_info is not None
        assert a.api_info.name in ("github", "slack")

    # ---- Code generation ----

    def test_multi_api_ts_generates_prefixed_auth(self, tmp_path):
        a = self.generator.analyze_prompt("Build GitHub and Slack tools")
        r = self.generator.generate(a, "multi-api-server", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "GITHUB_BASE_URL" in content
        assert "GITHUB_HEADERS" in content
        assert "SLACK_BASE_URL" in content
        assert "SLACK_HEADERS" in content
        assert "GITHUB_TOKEN" in content
        assert "SLACK_BOT_TOKEN" in content

    def test_multi_api_py_generates_prefixed_auth(self, tmp_path):
        a = self.generator.analyze_prompt("Build GitHub and Slack tools")
        r = self.generator.generate(a, "multi-api-server", "python", tmp_path)
        assert r.success
        content = (r.output_path / "server.py").read_text(encoding="utf-8")
        assert "GITHUB_BASE_URL" in content
        assert "GITHUB_HEADERS" in content
        assert "SLACK_BASE_URL" in content
        assert "SLACK_HEADERS" in content

    def test_multi_api_env_file(self, tmp_path):
        a = self.generator.analyze_prompt("GitHub and Stripe integration")
        r = self.generator.generate(a, "multi-env", "typescript", tmp_path)
        assert r.success
        env = (r.output_path / ".env.example").read_text(encoding="utf-8")
        assert "GITHUB_TOKEN" in env
        assert "STRIPE_SECRET_KEY" in env

    def test_multi_api_setup_guide(self, tmp_path):
        a = self.generator.analyze_prompt("GitHub and Slack tools")
        r = self.generator.generate(a, "multi-setup", "typescript", tmp_path)
        assert r.success
        setup = (r.output_path / "SETUP.md").read_text(encoding="utf-8")
        assert "GitHub" in setup
        assert "Slack" in setup

    def test_multi_api_tools_from_both_apis(self, tmp_path):
        a = self.generator.analyze_prompt("Build GitHub and Slack tools")
        r = self.generator.generate(a, "multi-tools", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        # Should have tools from both APIs
        assert "gh_list_repos" in content
        assert "slack_list_channels" in content

    def test_single_api_backward_compat_aliases(self, tmp_path):
        """Single-API servers should still generate BASE_URL and headers aliases."""
        a = self.generator.analyze_prompt("Build GitHub API tools")
        r = self.generator.generate(a, "single-api", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "GITHUB_BASE_URL" in content
        assert "const BASE_URL = GITHUB_BASE_URL" in content

    # ---- Parser ----

    def test_parser_handles_api_names_array(self):
        """parse_analysis_response should handle both old api_name and new api_names."""
        from mcp_factory.llm.prompts import parse_analysis_response
        data = {
            "intent": "Multi-API server",
            "template": "api-wrapper",
            "api_names": ["github", "slack"],
            "prefix": "multi_",
            "tools": [{"name": "gh_list", "description": "List repos"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["api_names"] == ["github", "slack"]

    def test_parser_filters_invalid_api_names(self):
        from mcp_factory.llm.prompts import parse_analysis_response
        data = {
            "intent": "test",
            "template": "api-wrapper",
            "api_names": ["github", "invalid-api", "slack"],
            "prefix": "x_",
            "tools": [{"name": "x_get", "description": "Get"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert "invalid-api" not in result["api_names"]
        assert "github" in result["api_names"]
        assert "slack" in result["api_names"]


class TestFallbackChain:
    """Test that engine falls back to keywords when LLM is unavailable."""

    def test_fallback_when_llm_unavailable(self):
        g = MCPGenerator(provider="ollama", model="nonexistent-model-xyz")
        a = g.analyze_prompt("Read my CSV files")
        assert a.parameters.get("source") == "keywords"
        assert a.template == "file-reader"
        assert not g._llm_used

    def test_keyword_fallback_still_detects_api(self):
        g = MCPGenerator(provider="ollama", model="nonexistent-model-xyz")
        a = g.analyze_prompt("Build GitHub API tools")
        assert a.parameters.get("source") == "keywords"
        assert a.api_info is not None
        assert a.api_info.name == "github"
        assert a.template == "api-wrapper"

    def test_generation_works_after_fallback(self, tmp_path):
        g = MCPGenerator(provider="ollama", model="nonexistent-model-xyz")
        a = g.analyze_prompt("Build Stripe API tools")
        r = g.generate(a, "stripe-tools", "typescript", tmp_path)
        assert r.success
        content = (r.output_path / "src" / "index.ts").read_text(encoding="utf-8")
        assert "STRIPE_SECRET_KEY" in content
        # Stage 2: Stripe should have specific tools
        assert "stripe_list_customers" in content


class TestCodeReviewer:
    """Test Stage 3: LLM code review."""

    # ---- Data model tests ----

    def test_review_issue_creation(self):
        from mcp_factory.llm.reviewer import ReviewIssue
        issue = ReviewIssue(
            severity="warning",
            category="security",
            message="Missing input validation",
            suggestion="Add input sanitization",
        )
        assert issue.severity == "warning"
        assert issue.category == "security"

    def test_code_review_counts(self):
        from mcp_factory.llm.reviewer import CodeReview, ReviewIssue
        review = CodeReview(
            score=7,
            summary="Decent code",
            issues=[
                ReviewIssue("error", "bug", "Null pointer"),
                ReviewIssue("error", "bug", "Type mismatch"),
                ReviewIssue("warning", "security", "Weak validation"),
                ReviewIssue("info", "style", "Consider renaming"),
            ],
        )
        assert review.error_count == 2
        assert review.warning_count == 1
        assert review.info_count == 1

    def test_code_review_no_issues(self):
        from mcp_factory.llm.reviewer import CodeReview
        review = CodeReview(score=10, summary="Perfect code")
        assert review.error_count == 0
        assert review.warning_count == 0
        assert review.reviewed is True

    # ---- Parsing tests ----

    def test_parse_valid_review(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        data = {
            "score": 8,
            "summary": "Well-structured MCP server",
            "issues": [
                {
                    "severity": "warning",
                    "category": "best-practice",
                    "message": "Missing pagination on list tool",
                    "line_hint": "api_get handler",
                    "suggestion": "Add offset/limit parameters",
                },
            ],
            "strengths": ["Good error handling", "Proper annotations"],
        }
        review = CodeReviewer._parse_review(data)
        assert review.score == 8
        assert review.summary == "Well-structured MCP server"
        assert len(review.issues) == 1
        assert review.issues[0].severity == "warning"
        assert review.issues[0].category == "best-practice"
        assert len(review.strengths) == 2

    def test_parse_clamps_score(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        # Score > 10 clamped to 10
        review = CodeReviewer._parse_review({"score": 15, "summary": "x", "issues": []})
        assert review.score == 10
        # Score < 1 clamped to 1
        review = CodeReviewer._parse_review({"score": -5, "summary": "x", "issues": []})
        assert review.score == 1

    def test_parse_normalizes_severity(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        data = {
            "score": 5,
            "summary": "test",
            "issues": [
                {"severity": "CRITICAL", "category": "bug", "message": "bad"},
                {"severity": "error", "category": "bug", "message": "also bad"},
            ],
        }
        review = CodeReviewer._parse_review(data)
        assert review.issues[0].severity == "info"  # unknown -> info
        assert review.issues[1].severity == "error"  # valid stays

    def test_parse_normalizes_category(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        data = {
            "score": 5,
            "summary": "test",
            "issues": [
                {"severity": "warning", "category": "unknown-cat", "message": "x"},
            ],
        }
        review = CodeReviewer._parse_review(data)
        assert review.issues[0].category == "style"  # unknown -> style

    def test_parse_empty_response(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        review = CodeReviewer._parse_review({})
        assert review.score == 1  # clamped from 0
        assert review.summary == "No summary provided"
        assert review.issues == []
        assert review.strengths == []

    def test_parse_skips_invalid_issues(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        data = {
            "score": 7,
            "summary": "test",
            "issues": [
                "not a dict",
                {"severity": "info", "category": "style", "message": "valid issue"},
                42,
            ],
        }
        review = CodeReviewer._parse_review(data)
        assert len(review.issues) == 1

    # ---- Integration tests ----

    def test_review_skipped_when_llm_unavailable(self):
        from mcp_factory.llm.reviewer import CodeReviewer
        llm = LLMClient(provider="ollama", model="nonexistent-xyz")
        reviewer = CodeReviewer(llm)
        review = reviewer.review(Path("/nonexistent"), "typescript")
        assert not review.reviewed
        assert review.score == 0

    def test_review_skipped_in_generation(self, tmp_path):
        """Without LLM, generation still works but review is None."""
        g = MCPGenerator(provider="ollama", model="nonexistent-xyz")
        a = g.analyze_prompt("Read CSV files")
        r = g.generate(a, "test-server", "typescript", tmp_path)
        assert r.success
        assert r.review is None  # LLM unavailable, review skipped

    def test_review_field_exists_on_result(self, tmp_path):
        """GenerationResult now has a review field."""
        g = MCPGenerator(provider="ollama")
        a = g.analyze_prompt("Build file reader")
        r = g.generate(a, "test-review-field", "python", tmp_path)
        assert r.success
        # review is None because Ollama isn't running, but field exists
        assert hasattr(r, "review")

    def test_review_missing_server_file(self, tmp_path):
        """Reviewer handles missing server file gracefully."""
        from mcp_factory.llm.reviewer import CodeReviewer
        # Create a fake LLM that reports available (to test file-not-found path)
        llm = LLMClient(provider="ollama")
        llm._available = True  # Force "available" to test file path
        reviewer = CodeReviewer(llm)
        review = reviewer.review(tmp_path / "nonexistent-dir", "typescript")
        assert not review.reviewed

    def test_review_prompts_exist(self):
        from mcp_factory.llm.reviewer import REVIEW_SYSTEM_PROMPT, REVIEW_USER_PROMPT
        assert "MCP" in REVIEW_SYSTEM_PROMPT
        assert "security" in REVIEW_SYSTEM_PROMPT.lower()
        assert "{code}" in REVIEW_USER_PROMPT
        assert "{language}" in REVIEW_USER_PROMPT


# ---------------------------------------------------------------------------
# Stage 4 tests — Template Expansion (auth-server, data-pipeline, notification-hub)
# ---------------------------------------------------------------------------

class TestAuthServerTemplate:
    """Test auth-server template detection and code generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_auth_detection_login(self):
        analysis = self.generator.analyze_prompt("Build a login system with JWT tokens")
        assert analysis.template == "auth-server"

    def test_auth_detection_register(self):
        analysis = self.generator.analyze_prompt("Create user registration and authentication")
        assert analysis.template == "auth-server"

    def test_auth_tools_present(self):
        analysis = self.generator.analyze_prompt("JWT auth server with user management")
        assert "auth_register" in analysis.tool_names
        assert "auth_login" in analysis.tool_names
        assert "auth_verify" in analysis.tool_names
        assert "auth_refresh" in analysis.tool_names
        assert "auth_list_users" in analysis.tool_names

    def test_auth_prefix(self):
        analysis = self.generator.analyze_prompt("Authentication server")
        assert analysis.prefix == "auth_"

    def test_auth_intent(self):
        analysis = self.generator.analyze_prompt("Build JWT authentication")
        assert "auth" in analysis.intent.lower() or "jwt" in analysis.intent.lower() or "token" in analysis.intent.lower()

    def test_generate_auth_typescript(self, tmp_path):
        analysis = self.generator.analyze_prompt("JWT auth server")
        result = self.generator.generate(analysis, "auth-test-ts", "typescript", tmp_path)
        assert result.success
        index = (tmp_path / "auth-test-ts" / "src" / "index.ts").read_text(encoding="utf-8")
        assert "auth_register" in index
        assert "auth_login" in index
        assert "JWT_SECRET" in index
        # Check template-specific deps
        pkg = (tmp_path / "auth-test-ts" / "package.json").read_text(encoding="utf-8")
        assert "jsonwebtoken" in pkg
        assert "bcryptjs" in pkg

    def test_generate_auth_python(self, tmp_path):
        analysis = self.generator.analyze_prompt("JWT auth server")
        result = self.generator.generate(analysis, "auth-test-py", "python", tmp_path)
        assert result.success
        server = (tmp_path / "auth-test-py" / "server.py").read_text(encoding="utf-8")
        assert "auth_register" in server
        assert "auth_login" in server
        assert "JWT_SECRET" in server
        # Check template-specific deps
        pyproject = (tmp_path / "auth-test-py" / "pyproject.toml").read_text(encoding="utf-8")
        assert "PyJWT" in pyproject

    def test_auth_env_file(self, tmp_path):
        analysis = self.generator.analyze_prompt("JWT auth server")
        result = self.generator.generate(analysis, "auth-env-test", "typescript", tmp_path)
        env = (tmp_path / "auth-env-test" / ".env.example").read_text(encoding="utf-8")
        assert "JWT_SECRET" in env
        assert "JWT_EXPIRY_HOURS" in env


class TestDataPipelineTemplate:
    """Test data-pipeline template detection and code generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_pipeline_detection_etl(self):
        analysis = self.generator.analyze_prompt("Build an ETL pipeline to process data")
        assert analysis.template == "data-pipeline"

    def test_pipeline_detection_transform(self):
        analysis = self.generator.analyze_prompt("Create a data pipeline to ingest and transform CSV files")
        assert analysis.template == "data-pipeline"

    def test_pipeline_tools_present(self):
        analysis = self.generator.analyze_prompt("Data processing pipeline")
        assert "pipe_ingest" in analysis.tool_names
        assert "pipe_transform" in analysis.tool_names
        assert "pipe_aggregate" in analysis.tool_names
        assert "pipe_export" in analysis.tool_names
        assert "pipe_status" in analysis.tool_names

    def test_pipeline_prefix(self):
        analysis = self.generator.analyze_prompt("ETL pipeline for batch processing")
        assert analysis.prefix == "pipe_"

    def test_generate_pipeline_typescript(self, tmp_path):
        analysis = self.generator.analyze_prompt("ETL pipeline to ingest CSV, transform and export")
        result = self.generator.generate(analysis, "pipe-test-ts", "typescript", tmp_path)
        assert result.success
        index = (tmp_path / "pipe-test-ts" / "src" / "index.ts").read_text(encoding="utf-8")
        assert "pipe_ingest" in index
        assert "pipe_transform" in index
        assert "pipe_aggregate" in index
        assert "pipe_export" in index

    def test_generate_pipeline_python(self, tmp_path):
        analysis = self.generator.analyze_prompt("ETL pipeline to ingest CSV, transform and export")
        result = self.generator.generate(analysis, "pipe-test-py", "python", tmp_path)
        assert result.success
        server = (tmp_path / "pipe-test-py" / "server.py").read_text(encoding="utf-8")
        assert "pipe_ingest" in server
        assert "pipe_transform" in server
        assert "pipe_aggregate" in server

    def test_pipeline_env_file(self, tmp_path):
        analysis = self.generator.analyze_prompt("ETL data pipeline")
        result = self.generator.generate(analysis, "pipe-env-test", "typescript", tmp_path)
        env = (tmp_path / "pipe-env-test" / ".env.example").read_text(encoding="utf-8")
        assert "PIPELINE_DATA_DIR" in env
        assert "MAX_ROWS" in env


class TestNotificationHubTemplate:
    """Test notification-hub template detection and code generation."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_notify_detection_email(self):
        analysis = self.generator.analyze_prompt("Send email notifications and alerts")
        assert analysis.template == "notification-hub"

    def test_notify_detection_webhook(self):
        analysis = self.generator.analyze_prompt("Build a notification system with webhook support")
        assert analysis.template == "notification-hub"

    def test_notify_tools_present(self):
        analysis = self.generator.analyze_prompt("Multi-channel notification hub")
        assert "notify_send" in analysis.tool_names
        assert "notify_list_channels" in analysis.tool_names
        assert "notify_history" in analysis.tool_names
        assert "notify_webhook" in analysis.tool_names

    def test_notify_prefix(self):
        analysis = self.generator.analyze_prompt("Notification system with email and webhook")
        assert analysis.prefix == "notify_"

    def test_generate_notify_typescript(self, tmp_path):
        analysis = self.generator.analyze_prompt("Notification hub with email and webhook")
        result = self.generator.generate(analysis, "notify-test-ts", "typescript", tmp_path)
        assert result.success
        index = (tmp_path / "notify-test-ts" / "src" / "index.ts").read_text(encoding="utf-8")
        assert "notify_send" in index
        assert "notify_list_channels" in index
        assert "SMTP_HOST" in index
        # Check template-specific deps
        pkg = (tmp_path / "notify-test-ts" / "package.json").read_text(encoding="utf-8")
        assert "nodemailer" in pkg

    def test_generate_notify_python(self, tmp_path):
        analysis = self.generator.analyze_prompt("Notification hub with email and webhook")
        result = self.generator.generate(analysis, "notify-test-py", "python", tmp_path)
        assert result.success
        server = (tmp_path / "notify-test-py" / "server.py").read_text(encoding="utf-8")
        assert "notify_send" in server
        assert "notify_list_channels" in server
        assert "SMTP_HOST" in server
        # Check template-specific deps
        pyproject = (tmp_path / "notify-test-py" / "pyproject.toml").read_text(encoding="utf-8")
        assert "httpx" in pyproject

    def test_notify_env_file(self, tmp_path):
        analysis = self.generator.analyze_prompt("Email notification hub")
        result = self.generator.generate(analysis, "notify-env-test", "python", tmp_path)
        env = (tmp_path / "notify-env-test" / ".env.example").read_text(encoding="utf-8")
        assert "SMTP_HOST" in env
        assert "SMTP_USER" in env
        assert "DEFAULT_FROM" in env

    def test_notify_webhook_hmac(self, tmp_path):
        """Webhook tool supports HMAC signatures."""
        analysis = self.generator.analyze_prompt("Webhook notification system")
        result = self.generator.generate(analysis, "notify-hmac-test", "typescript", tmp_path)
        index = (tmp_path / "notify-hmac-test" / "src" / "index.ts").read_text(encoding="utf-8")
        assert "X-Signature-256" in index


class TestTemplateExpansionIntegration:
    """Cross-cutting tests for the 8-template system."""

    def setup_method(self):
        self.generator = MCPGenerator(provider="ollama")

    def test_all_8_templates_in_keywords(self):
        from mcp_factory.generator.engine import TEMPLATE_KEYWORDS
        expected = {"file-reader", "database-connector", "api-wrapper", "web-scraper",
                    "document-processor", "auth-server", "data-pipeline", "notification-hub"}
        assert set(TEMPLATE_KEYWORDS.keys()) == expected

    def test_all_8_templates_in_tools(self):
        from mcp_factory.generator.engine import TEMPLATE_TOOLS
        expected = {"file-reader", "database-connector", "api-wrapper", "web-scraper",
                    "document-processor", "auth-server", "data-pipeline", "notification-hub"}
        assert set(TEMPLATE_TOOLS.keys()) == expected

    def test_all_8_templates_in_intent_map(self):
        from mcp_factory.generator.engine import INTENT_MAP
        expected = {"file-reader", "database-connector", "api-wrapper", "web-scraper",
                    "document-processor", "auth-server", "data-pipeline", "notification-hub"}
        assert set(INTENT_MAP.keys()) == expected

    def test_no_keyword_overlap_new_templates(self):
        """New templates shouldn't accidentally steal prompts from existing ones."""
        # A generic file prompt should NOT match auth-server
        a = self.generator.analyze_prompt("Read my text files and parse them")
        assert a.template == "file-reader"
        # A database prompt should NOT match data-pipeline
        a = self.generator.analyze_prompt("Connect to PostgreSQL and run SQL queries")
        assert a.template == "database-connector"


# ---------------------------------------------------------------------------
# Stage 5 tests — Interactive Mode (PromptRefiner)
# ---------------------------------------------------------------------------

class TestPromptQuality:
    """Test prompt quality scoring and vagueness detection."""

    def test_short_prompt_is_vague(self):
        from mcp_factory.llm.interactive import is_prompt_vague
        assert is_prompt_vague("build a server")

    def test_very_short_is_vague(self):
        from mcp_factory.llm.interactive import is_prompt_vague
        assert is_prompt_vague("api")

    def test_detailed_prompt_is_not_vague(self):
        from mcp_factory.llm.interactive import is_prompt_vague
        assert not is_prompt_vague("Build a GitHub API wrapper that can list repos, create issues, and read pull requests using JWT authentication")

    def test_medium_with_specifics_is_not_vague(self):
        from mcp_factory.llm.interactive import is_prompt_vague
        assert not is_prompt_vague("Read CSV files and filter rows by column values then export as JSON")

    def test_quality_score_ranges(self):
        from mcp_factory.llm.interactive import prompt_quality_score
        # Very vague
        score_vague = prompt_quality_score("make server")
        # Very specific
        score_specific = prompt_quality_score("Build a PostgreSQL database connector to query customer tables, insert records, and export CSV reports with pagination")
        assert score_vague < score_specific
        assert 0.0 <= score_vague <= 1.0
        assert 0.0 <= score_specific <= 1.0

    def test_quality_score_specific_keywords_boost(self):
        from mcp_factory.llm.interactive import prompt_quality_score
        # Same length, one has specifics
        generic = prompt_quality_score("build a thing that does stuff with things")
        specific = prompt_quality_score("build a github api wrapper with jwt login")
        assert specific > generic


class TestFollowUpQuestions:
    """Test follow-up question generation."""

    def test_fallback_questions_for_each_template(self):
        from mcp_factory.llm.interactive import TEMPLATE_QUESTIONS
        # All 8 templates should have fallback questions
        expected = {"file-reader", "database-connector", "api-wrapper", "web-scraper",
                    "document-processor", "auth-server", "data-pipeline", "notification-hub"}
        assert set(TEMPLATE_QUESTIONS.keys()) == expected

    def test_each_template_has_at_least_2_questions(self):
        from mcp_factory.llm.interactive import TEMPLATE_QUESTIONS
        for template, questions in TEMPLATE_QUESTIONS.items():
            assert len(questions) >= 2, f"{template} has fewer than 2 questions"

    def test_questions_have_required_fields(self):
        from mcp_factory.llm.interactive import TEMPLATE_QUESTIONS
        for template, questions in TEMPLATE_QUESTIONS.items():
            for q in questions:
                assert q.question, f"Missing question text in {template}"
                assert q.key, f"Missing key in {template}"

    def test_refiner_generates_questions_without_llm(self):
        from mcp_factory.llm.interactive import PromptRefiner
        refiner = PromptRefiner(llm=None)
        questions = refiner.generate_questions("build a server", "file-reader", "File processing")
        assert len(questions) >= 2
        assert all(q.question for q in questions)

    def test_refiner_generates_questions_for_api_wrapper(self):
        from mcp_factory.llm.interactive import PromptRefiner
        refiner = PromptRefiner(llm=None)
        questions = refiner.generate_questions("api server", "api-wrapper", "REST API")
        assert any("API" in q.question or "api" in q.question.lower() for q in questions)

    def test_refiner_needs_refinement(self):
        from mcp_factory.llm.interactive import PromptRefiner
        refiner = PromptRefiner()
        assert refiner.needs_refinement("build server")
        assert not refiner.needs_refinement("Build a GitHub API wrapper that lists repos and creates issues with authentication")

    def test_refiner_fallback_for_unknown_template(self):
        from mcp_factory.llm.interactive import PromptRefiner
        refiner = PromptRefiner(llm=None)
        # Even with a template not in TEMPLATE_QUESTIONS, should return generic questions
        questions = refiner.generate_questions("something", "nonexistent-template", "test")
        assert len(questions) >= 1


class TestEnhancedPrompt:
    """Test prompt enhancement from follow-up answers."""

    def test_build_enhanced_prompt(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        refiner = PromptRefiner()
        questions = [
            FollowUpQuestion("What database?", "db", ["PostgreSQL", "MySQL"]),
            FollowUpQuestion("Read or write?", "mode", ["Read-only", "Read/write"]),
        ]
        answers = {"db": "PostgreSQL", "mode": "Read/write"}
        result = refiner.build_enhanced_prompt("database server", questions, answers)
        assert result.was_refined
        assert "PostgreSQL" in result.enhanced_prompt
        assert "Read/write" in result.enhanced_prompt
        assert "database server" in result.enhanced_prompt

    def test_no_refinement_when_no_answers(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        refiner = PromptRefiner()
        questions = [FollowUpQuestion("What?", "q1")]
        answers = {}
        result = refiner.build_enhanced_prompt("test prompt", questions, answers)
        assert not result.was_refined
        assert result.enhanced_prompt == "test prompt"

    def test_enhanced_prompt_uses_defaults(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        refiner = PromptRefiner()
        questions = [FollowUpQuestion("What db?", "db", default="SQLite")]
        answers = {"db": ""}  # empty answer, should use default
        # Default is used in build_enhanced_prompt only if answer is non-empty
        result = refiner.build_enhanced_prompt("make db server", questions, answers)
        # Empty answer means no refinement for this question
        assert not result.was_refined

    def test_result_tracks_original_prompt(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        refiner = PromptRefiner()
        questions = [FollowUpQuestion("Which API?", "api")]
        answers = {"api": "GitHub"}
        result = refiner.build_enhanced_prompt("api wrapper", questions, answers)
        assert result.original_prompt == "api wrapper"
        assert result.questions_asked == questions
        assert result.answers == answers

    def test_multiple_answers_combined(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        refiner = PromptRefiner()
        questions = [
            FollowUpQuestion("Format?", "format"),
            FollowUpQuestion("Operations?", "ops"),
            FollowUpQuestion("Scale?", "scale"),
        ]
        answers = {"format": "CSV", "ops": "filter and aggregate", "scale": "up to 1M rows"}
        result = refiner.build_enhanced_prompt("data pipeline", questions, answers)
        assert result.was_refined
        assert "CSV" in result.enhanced_prompt
        assert "filter and aggregate" in result.enhanced_prompt
        assert "1M rows" in result.enhanced_prompt


class TestInteractiveLLMQuestions:
    """Test LLM-powered question generation (mocked)."""

    def test_llm_question_parsing_valid(self):
        from mcp_factory.llm.interactive import PromptRefiner, FollowUpQuestion
        # Simulate what _generate_with_llm would parse
        raw = {
            "questions": [
                {"question": "Which API?", "key": "api", "choices": ["GitHub", "Slack"], "default": ""},
                {"question": "Read or write?", "key": "mode"},
            ]
        }
        # Test the parsing logic directly
        questions = []
        for q in raw["questions"]:
            questions.append(FollowUpQuestion(
                question=q.get("question", ""),
                key=q.get("key", ""),
                choices=q.get("choices", []),
                default=q.get("default", ""),
            ))
        assert len(questions) == 2
        assert questions[0].choices == ["GitHub", "Slack"]
        assert questions[1].choices == []

    def test_llm_question_system_prompt_exists(self):
        from mcp_factory.llm.interactive import QUESTION_SYSTEM_PROMPT, QUESTION_USER_PROMPT
        assert "follow-up" in QUESTION_SYSTEM_PROMPT.lower() or "question" in QUESTION_SYSTEM_PROMPT.lower()
        assert "{prompt}" in QUESTION_USER_PROMPT
        assert "{template}" in QUESTION_USER_PROMPT

    def test_refiner_with_unavailable_llm_falls_back(self):
        from mcp_factory.llm.interactive import PromptRefiner
        llm = LLMClient(provider="ollama", model="nonexistent-xyz-model")
        refiner = PromptRefiner(llm=llm)
        questions = refiner.generate_questions("build server", "file-reader", "file processing")
        # Should fall back to template questions since LLM is unavailable
        assert len(questions) >= 2


class TestPromptParserUpdated:
    """Test that parse_analysis_response accepts all 8 templates."""

    def test_auth_server_template_accepted(self):
        data = {
            "intent": "JWT auth",
            "template": "auth-server",
            "tools": [{"name": "auth_login", "description": "Login"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["template"] == "auth-server"

    def test_data_pipeline_template_accepted(self):
        data = {
            "intent": "ETL pipeline",
            "template": "data-pipeline",
            "tools": [{"name": "pipe_ingest", "description": "Ingest data"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["template"] == "data-pipeline"

    def test_notification_hub_template_accepted(self):
        data = {
            "intent": "Send notifications",
            "template": "notification-hub",
            "tools": [{"name": "notify_send", "description": "Send notification"}],
        }
        result = parse_analysis_response(data)
        assert result is not None
        assert result["template"] == "notification-hub"


# ==================================================================
# Config Export Tests
# ==================================================================


class TestConfigExport:
    """Test Claude Desktop config generation."""

    def test_build_server_entry_typescript(self):
        from mcp_factory.config import build_server_entry
        entry = build_server_entry("my-server", "typescript", "/path/to/server")
        assert entry["command"] == "node"
        assert entry["args"][0].endswith("index.js")
        assert "env" not in entry

    def test_build_server_entry_python(self):
        from mcp_factory.config import build_server_entry
        entry = build_server_entry("my-server", "python", "/path/to/server")
        assert entry["command"] == "python"
        assert entry["args"][0].endswith("server.py")

    def test_build_server_entry_with_env_vars(self):
        from mcp_factory.config import build_server_entry
        entry = build_server_entry("gh-tools", "typescript", "/path/to/server", env_vars={"GITHUB_TOKEN": "xxx"})
        assert entry["env"] == {"GITHUB_TOKEN": "xxx"}

    def test_generate_config_snippet(self):
        from mcp_factory.config import generate_config_snippet
        import json
        snippet = generate_config_snippet("test-server", "typescript", "/output/test-server")
        parsed = json.loads(snippet)
        assert "mcpServers" in parsed
        assert "test-server" in parsed["mcpServers"]
        assert parsed["mcpServers"]["test-server"]["command"] == "node"

    def test_generate_config_snippet_python(self):
        from mcp_factory.config import generate_config_snippet
        import json
        snippet = generate_config_snippet("py-server", "python", "/output/py-server")
        parsed = json.loads(snippet)
        assert parsed["mcpServers"]["py-server"]["command"] == "python"


class TestConfigReadWrite:
    """Test config file read/write operations."""

    def test_read_config_nonexistent(self, tmp_path):
        from mcp_factory.config import read_config
        config = read_config(tmp_path / "nonexistent.json")
        assert config == {"mcpServers": {}}

    def test_write_and_read_config(self, tmp_path):
        from mcp_factory.config import write_config, read_config
        config_path = tmp_path / "claude_config.json"
        original = {"mcpServers": {"test": {"command": "node", "args": ["/test"]}}}
        write_config(original, config_path)
        loaded = read_config(config_path)
        assert loaded["mcpServers"]["test"]["command"] == "node"

    def test_add_server_to_config(self, tmp_path):
        from mcp_factory.config import add_server_to_config, read_config
        config_path = tmp_path / "claude_config.json"
        path, was_added = add_server_to_config("my-server", "typescript", "/output/my-server", config_path=config_path)
        assert was_added is True
        config = read_config(config_path)
        assert "my-server" in config["mcpServers"]

    def test_add_server_no_overwrite(self, tmp_path):
        from mcp_factory.config import add_server_to_config
        config_path = tmp_path / "claude_config.json"
        add_server_to_config("server-a", "typescript", "/output/a", config_path=config_path)
        _, was_added = add_server_to_config("server-a", "python", "/output/b", config_path=config_path, overwrite=False)
        assert was_added is False

    def test_add_server_overwrite(self, tmp_path):
        from mcp_factory.config import add_server_to_config, read_config
        config_path = tmp_path / "claude_config.json"
        add_server_to_config("server-a", "typescript", "/output/a", config_path=config_path)
        add_server_to_config("server-a", "python", "/output/b", config_path=config_path, overwrite=True)
        config = read_config(config_path)
        assert config["mcpServers"]["server-a"]["command"] == "python"

    def test_remove_server_from_config(self, tmp_path):
        from mcp_factory.config import add_server_to_config, remove_server_from_config, read_config
        config_path = tmp_path / "claude_config.json"
        add_server_to_config("to-delete", "typescript", "/output/del", config_path=config_path)
        removed = remove_server_from_config("to-delete", config_path=config_path)
        assert removed is True
        config = read_config(config_path)
        assert "to-delete" not in config["mcpServers"]

    def test_remove_nonexistent_server(self, tmp_path):
        from mcp_factory.config import remove_server_from_config
        config_path = tmp_path / "claude_config.json"
        removed = remove_server_from_config("ghost", config_path=config_path)
        assert removed is False

    def test_export_all_servers(self, tmp_path):
        from mcp_factory.config import export_all_servers, read_config
        config_path = tmp_path / "claude_config.json"
        servers = [
            {"name": "s1", "language": "typescript", "output_path": "/out/s1"},
            {"name": "s2", "language": "python", "output_path": "/out/s2"},
        ]
        path, count = export_all_servers(servers, config_path)
        assert count == 2
        config = read_config(config_path)
        assert "s1" in config["mcpServers"]
        assert "s2" in config["mcpServers"]
        assert config["mcpServers"]["s1"]["command"] == "node"
        assert config["mcpServers"]["s2"]["command"] == "python"

    def test_preserves_existing_config(self, tmp_path):
        from mcp_factory.config import write_config, add_server_to_config, read_config
        config_path = tmp_path / "claude_config.json"
        write_config({"mcpServers": {"existing": {"command": "node", "args": ["/x"]}}, "otherKey": True}, config_path)
        add_server_to_config("new-server", "python", "/out/new", config_path=config_path)
        config = read_config(config_path)
        assert "existing" in config["mcpServers"]
        assert "new-server" in config["mcpServers"]
        assert config["otherKey"] is True


class TestConfigPath:
    """Test OS-specific config path detection."""

    def test_get_claude_config_path_returns_path(self):
        from mcp_factory.config import get_claude_config_path
        path = get_claude_config_path()
        assert isinstance(path, Path)
        assert "claude_desktop_config.json" in str(path).lower() or "claude" in str(path).lower()

    def test_config_path_is_in_user_home(self):
        from mcp_factory.config import get_claude_config_path
        path = get_claude_config_path()
        assert str(Path.home()) in str(path)
