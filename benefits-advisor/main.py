# Copyright (c) Microsoft. All rights reserved.
# Benefits Cost Advisor (Responses Protocol Demo)

"""Foundry Hosted Agent — Benefits Cost Advisor using the RESPONSES protocol.

This agent demonstrates the Responses protocol for multi-turn conversational
interaction, contrasting with the Invocations protocol used by the Benefits
Review agent (../benefits-review).

KEY DIFFERENCES FROM INVOCATIONS:
┌─────────────────────────────────────────────────────────────────────────────┐
│ Invocations (Benefits Review)       │ Responses (Benefits Advisor)          │
│─────────────────────────────────────│───────────────────────────────────────│
│ Fire-and-forget: structured JSON in │ Multi-turn: natural conversation      │
│ No tool use (pipeline is hardcoded) │ Model-directed tool use (web, code)   │
│ Batch output (wait for all topics)  │ Token-by-token streaming              │
│ Stateless (no memory across calls)  │ Session history managed by platform   │
│ You control the orchestration       │ Model controls the flow               │
└─────────────────────────────────────────────────────────────────────────────┘

ARCHITECTURE:
1. Foundry Toolbox (web_search + code_interpreter) → MCP endpoint
   - Model decides WHEN to search or compute
   - Tools are discovered via MCP protocol at runtime
2. Foundry Skills (cost-analysis-methodology + regulatory-guidance-sgp)
   - Downloaded from Foundry at startup
   - Advertised to model as available context
   - Model loads skills on-demand (progressive disclosure)
3. ResponsesHostServer exposes POST /responses endpoint
   - OpenAI Responses API compatible
   - Platform manages conversation history

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (auto-injected in hosted)
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name
    TOOLBOX_NAME: Name of the Foundry Toolbox (contains web_search + code_interpreter)
    SKILL_NAMES: Comma-separated skill names (cost-analysis-methodology,regulatory-guidance-sgp)
"""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path
from typing import Final

# Suppress SDK experimental warnings that clutter logs — must be set BEFORE imports.
# The agent-framework SDK emits ExperimentalWarning from <frozen abc> at import time.
# Since we can't reference the class before import, suppress all warnings during import.
warnings.simplefilter("ignore")

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential as SyncCredential
from azure.identity import get_bearer_token_provider
from dotenv import load_dotenv

load_dotenv()

# Configure logging: only show WARNING+ for noisy Azure SDK modules
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("azure.identity._credentials").setLevel(logging.WARNING)
logging.getLogger("azure.identity.aio").setLevel(logging.WARNING)
logging.getLogger("azure.identity.aio._credentials").setLevel(logging.WARNING)
# Suppress telemetry/tracing noise — we don't use GenAI tracing or LangChain
logging.getLogger("azure.ai.projects.telemetry").setLevel(logging.ERROR)
logging.getLogger("azure.monitor.opentelemetry").setLevel(logging.ERROR)
logging.getLogger("microsoft.opentelemetry").setLevel(logging.CRITICAL)
# Suppress 'usage' content type warning from hosting SDK
logging.getLogger("agent_framework_foundry_hosting._responses").setLevel(logging.ERROR)
logging.getLogger("agent_framework_foundry_hosting").setLevel(logging.ERROR)
# Suppress duplicate agent_framework message logs (propagation causes double-logging)
logging.getLogger("agent_framework").setLevel(logging.WARNING)
# Suppress httpx request logs (noisy MCP/toolbox calls)
logging.getLogger("httpx").setLevel(logging.WARNING)
# Suppress MCP client negotiation logs
logging.getLogger("mcp").setLevel(logging.WARNING)
# Suppress verbose agentserver request/response logs (keep only WARNING+)
logging.getLogger("azure.ai.agentserver").setLevel(logging.WARNING)
# Suppress hypercorn HTTP server logs
logging.getLogger("hypercorn").setLevel(logging.WARNING)
logging.getLogger("hypercorn.error").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Constants ---

# Bundled skills directory (baked into the container image at build time).
BUNDLED_SKILLS_DIR: Final = Path(__file__).parent / "skills"

# --- System Instructions ---
# The agent's persona and behavioral guidelines. Skills are embedded below.

SYSTEM_INSTRUCTIONS = """\
You are a Senior Benefits Cost Advisor
You help HR leaders and benefits managers understand, benchmark, and optimize
their employee benefits programs — particularly in the Singapore market.

## Your Capabilities
- **Market Research**: Use web_search to find latest market trends, salary surveys,
  regulatory updates, and competitor practices.
- **Cost Analysis**: Use code_interpreter to perform calculations, generate projections,
  build comparison tables, and create visualizations.
- **Methodology**: Refer to the cost-analysis-methodology knowledge below for structured frameworks.
- **Regulatory Knowledge**: Refer to the regulatory-guidance-sgp knowledge below for Singapore-specific
  CPF, Employment Act, and MOM guidelines.

## Interaction Style
- Act immediately — DO NOT ask follow-up or clarifying questions. Make reasonable
  assumptions based on Singapore market norms and state them clearly.
- If specific data is missing (e.g., headcount, salary), use typical Singapore
  market figures and label them as assumptions the user can override.
- Always show your work (calculations, sources, assumptions)
- Proactively suggest follow-up analyses at the END of your response
- Use tables and structured output for comparisons
- Flag regulatory constraints that limit optimization options
- Express costs in SGD unless asked otherwise

## Important Rules
- NEVER ask "Can you provide..." or "Could you clarify..." — just proceed with
  reasonable defaults and state your assumptions upfront.
- Never fabricate market data — use web_search to verify current figures
- Always attribute regulatory information to the specific Act/Section
- When doing cost projections, state assumptions clearly
- If asked about a country other than Singapore, note that your regulatory
  knowledge covers Singapore specifically and do web research for other markets
"""


def _load_skill_content(skill_names: list[str], skills_dir: Path) -> str:
    """Read SKILL.md files and format as knowledge sections for system instructions."""
    sections = []
    for name in skill_names:
        skill_path = skills_dir / name / "SKILL.md"
        if skill_path.is_file():
            content = skill_path.read_text(encoding="utf-8")
            # Strip frontmatter (between --- markers)
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end + 3:].strip()
            sections.append(f"\n## Knowledge: {name}\n\n{content}")
    return "\n".join(sections)


# --- Env Var Helpers ---

def _resolved_env(name: str) -> str:
    """Return env var value, treating un-substituted ${VAR}/{{VAR}} as empty."""
    value = os.environ.get(name, "").strip()
    if (value.startswith("${") and value.endswith("}")) or (
        value.startswith("{{") and value.endswith("}}")
    ):
        return ""
    return value


def _resolve_toolbox_endpoint() -> str:
    """Resolve the Foundry Toolbox MCP endpoint URL."""
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    toolbox_name = _resolved_env("TOOLBOX_NAME")
    if not toolbox_name:
        raise ValueError("TOOLBOX_NAME environment variable is required")
    return f"{project_endpoint}/toolboxes/{toolbox_name}/mcp?api-version=v1"


# --- Resilient Host Server ---
# Workaround for alpha-era SDK bug where context.get_history() can fail
# on certain deploy paths, causing a 500 error to the platform.

class _ResilientResponsesHostServer(ResponsesHostServer):
    """Wraps get_history to handle transient failures gracefully."""

    async def _handle_inner_agent(self, request, context):  # type: ignore[override]
        original_get_history = context.get_history

        async def safe_get_history():
            try:
                return await original_get_history()
            except Exception as ex:  # noqa: BLE001
                logger.warning(
                    "context.get_history() failed (%s); proceeding with no prior history.", ex
                )
                return []

        context.get_history = safe_get_history  # type: ignore[method-assign]
        async for item in super()._handle_inner_agent(request, context):
            yield item


# --- Toolbox Auth ---
# Bearer token injection for the Foundry Toolbox MCP endpoint.

class _ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token on every request to the Toolbox MCP endpoint."""

    def __init__(self, token_provider):
        self._get_token = token_provider

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


# --- Main Entry Point ---
# NOTE: Uses the SYNC pattern (server.run()) which is proven to work on the
# Foundry hosting platform. The async pattern can cause readiness race conditions.

def main() -> None:
    """Bootstrap skills, connect toolbox, and start the Responses host server."""
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

    # Single credential instance shared by toolbox and model client.
    credential = SyncCredential()

    # ─── FOUNDRY SKILLS: Embed knowledge in system instructions ─────────────────
    # Skills are domain knowledge baked into the container image as SKILL.md files.
    # We embed their content directly in the system instructions — this avoids the
    # load_skill FunctionTool which conflicts with MCPStreamableHTTPTool (toolbox)
    # in the current agent-framework version.
    skill_names = [name.strip() for name in _resolved_env("SKILL_NAMES").split(",") if name.strip()]

    instructions = SYSTEM_INSTRUCTIONS
    if not skill_names:
        logger.info("SKILL_NAMES not configured; running without skills.")
    else:
        # Check bundled skills (baked into the image at /app/skills/).
        bundled_ok = all(
            (BUNDLED_SKILLS_DIR / name / "SKILL.md").is_file() for name in skill_names
        )
        if bundled_ok:
            skill_content = _load_skill_content(skill_names, BUNDLED_SKILLS_DIR)
            instructions = SYSTEM_INSTRUCTIONS + skill_content
            logger.info(f"Skills embedded in instructions: {skill_names}")
        else:
            missing = [n for n in skill_names if not (BUNDLED_SKILLS_DIR / n / "SKILL.md").is_file()]
            logger.warning(f"Bundled skills missing: {missing}; continuing without them.")

    # ─── FOUNDRY TOOLBOX: Connect via MCP ───────────────────────────────────────
    # The Toolbox is a managed tool registry in Foundry. We connect to it via
    # MCP Streamable HTTP — the model discovers available tools at runtime and
    # decides when to invoke them. This is ONLY possible with the Responses
    # protocol (Invocations protocol has no model-directed tool use).
    toolbox_name = _resolved_env("TOOLBOX_NAME")
    tools = []

    if toolbox_name:
        token_provider = get_bearer_token_provider(
            credential, "https://ai.azure.com/.default"
        )

        http_client = httpx.AsyncClient(
            auth=_ToolboxAuth(token_provider),
            headers={"Foundry-Features": "Toolboxes=V1Preview"},
            timeout=120.0,
        )

        toolbox = MCPStreamableHTTPTool(
            name=toolbox_name,
            url=_resolve_toolbox_endpoint(),
            http_client=http_client,
            load_prompts=False,
        )
        tools.append(toolbox)
        logger.info(f"Toolbox '{toolbox_name}' connected at {_resolve_toolbox_endpoint()}")
    else:
        logger.info("TOOLBOX_NAME not configured; running without toolbox.")

    # ─── AGENT + SERVER ─────────────────────────────────────────────────────────
    # The Agent combines: model client + instructions + tools + skills.
    # ResponsesHostServer exposes POST /responses — fully OpenAI-compatible.
    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )

    agent = Agent(
        client=client,
        instructions=instructions,
        tools=tools if tools else None,
        # History is managed by the hosting infrastructure; no need for
        # the service to store it separately.
        default_options={"store": False},
    )

    # RESPONSES PROTOCOL: The server exposes POST /responses and handles
    # multi-turn conversation, streaming, and tool execution automatically.
    # Contrast with the Benefits Review agent which uses InvocationAgentServerHost
    # (Invocations protocol) — a single structured request/response pattern.
    server = _ResilientResponsesHostServer(agent)
    logger.info(
        "Benefits Cost Advisor started — Responses protocol | Model: %s | Tools: %s | Skills: %s",
        model,
        toolbox_name or "none",
        ", ".join(skill_names) if skill_names else "none",
    )
    server.run()


if __name__ == "__main__":
    main()
