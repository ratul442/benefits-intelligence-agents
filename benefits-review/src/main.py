"""Foundry Hosted Agent entry point — BYO Invocations protocol.

This agent implements the Benefits Review pipeline as a Microsoft Foundry
hosted agent using the Invocations protocol. BOL sends structured JSON
(company payload, market payload, datapoints catalog) and receives a
structured JSON response with the extracted Benefits Review report.

The azure-ai-agentserver-invocations SDK handles the HTTP contract,
health endpoints, and OpenTelemetry tracing. We supply the handler logic.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint (auto-injected in hosted containers)
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name (declared in agent.manifest.yaml)
"""

from __future__ import annotations

import json
import logging
import os
import traceback
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from azure.ai.agentserver.invocations import InvocationAgentServerHost

# Instrument OpenAI SDK to emit GenAI spans (picked up by agent-framework-foundry-hosting exporter)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
OpenAIInstrumentor().instrument()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Catalog loader ---
_catalog_data = None
_catalog_version = ""


def _load_catalog():
    """Load the hardened catalog from file at startup."""
    global _catalog_data, _catalog_version
    if _catalog_data is not None:
        return

    catalog_paths = [
        os.path.join(os.path.dirname(__file__), "..", "data", "catalog", "datapoints_catalog.json"),
        "/app/data/catalog/datapoints_catalog.json",  # Docker container path
    ]

    for path in catalog_paths:
        if os.path.isfile(path):
            with open(path) as f:
                raw = json.load(f)
            # Handle wrapped format (with metadata) or flat array
            if isinstance(raw, dict) and "items" in raw:
                _catalog_data = raw["items"]
                _catalog_version = raw.get("catalog_version", "")
            elif isinstance(raw, list):
                _catalog_data = raw
                _catalog_version = "legacy-flat"
            logger.info("Loaded catalog: %d items, version=%s", len(_catalog_data), _catalog_version)
            return

    logger.warning("Catalog file not found — will require catalog in request payload")
    _catalog_data = []


_load_catalog()

# Push catalog version into settings for downstream use
from src.config import settings as _settings
_settings.catalog_version = _catalog_version

# --- Lazy initialization (deferred to first request) ---
_openai_client = None
_model = None
_init_error = None


async def _ensure_initialized():
    """Initialize Foundry SDK clients on first use."""
    global _openai_client, _model, _init_error
    if _openai_client is not None:
        return
    if _init_error is not None:
        return  # Already tried and failed

    try:
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential
        from src.config import settings

        endpoint = settings.foundry_project_endpoint
        model = settings.azure_ai_model_deployment_name

        logger.info("Initializing agent — endpoint=%s, model=%s", endpoint, model)
        logger.info("Environment vars: %s", {k: v for k, v in os.environ.items() if "FOUNDRY" in k or "AZURE" in k or "MODEL" in k})

        if not endpoint:
            _init_error = "FOUNDRY_PROJECT_ENDPOINT not set"
            logger.error(_init_error)
            return
        if not model:
            _init_error = "AZURE_AI_MODEL_DEPLOYMENT_NAME not set"
            logger.error(_init_error)
            return

        credential = DefaultAzureCredential()
        project_client = AIProjectClient(endpoint=endpoint, credential=credential)
        _openai_client = project_client.get_openai_client()
        _model = model
        logger.info("Agent initialized successfully")
    except Exception as exc:
        _init_error = f"{type(exc).__name__}: {exc}"
        logger.error("Failed to initialize: %s", _init_error, exc_info=True)


# --- Invocations Host ---

app = InvocationAgentServerHost()


@app.invoke_handler
async def handle_invoke(request: Request):
    """Handle invocation. Always returns 200 with SSE body."""
    session_id = getattr(request.state, "session_id", None)
    invocation_id = getattr(request.state, "invocation_id", None)
    logger.info("=== INVOCATION %s (session %s) ===", invocation_id, session_id)

    try:
        body = await request.body()
        body_str = body.decode("utf-8", errors="replace") if body else ""
        logger.info("Body (%d bytes): %.200s", len(body_str), body_str)
    except Exception as exc:
        logger.error("Failed to read body: %s", exc, exc_info=True)
        body_str = ""

    # Diagnostic mode: return echo for simple payloads
    try:
        data = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        data = {"raw_input": body_str}

    if not isinstance(data, dict):
        data = {"raw_input": str(data)}

    # Unwrap Foundry invocations protocol {"input": {...}} envelope
    # If input is a string, it's a playground chat message
    if "input" in data and isinstance(data["input"], dict):
        data = data["input"]
    elif "input" in data and isinstance(data["input"], str):
        # Foundry playground sends {"input": "user text", "stream": true}
        data["message"] = data.pop("input")

    # If no company_payload (also accept company_profile as alias), handle as portal chat or diagnostic echo
    company_payload = data.get("company_payload") or data.get("company_profile", "")
    market_payload = data.get("market_payload") or data.get("market_profile", "")

    if not company_payload:
        logger.info("Chat/echo mode (no company_payload)")
        await _ensure_initialized()  # Initialize early to report status accurately
        user_message = data.get("message", None)
        stream = data.get("stream", True)

        # Portal playground sends {"message": "...", "stream": true/false}
        if user_message is not None:
            agent_version = os.environ.get("FOUNDRY_AGENT_VERSION", "latest")
            response_text = (
                f"✅ Agent is running (v{agent_version}). Received your message: \"{user_message}\"\n\n"
                f"This agent processes structured Benefits Review payloads.\n"
                f"To invoke the full pipeline, send a JSON body with:\n"
                f"- `company_payload` (markdown)\n"
                f"- `market_payload` (markdown)\n"
                f"- `datapoints_catalog` (array)\n\n"
                f"Session: {session_id}\n"
                f"Init status: {'OK' if _init_error is None else _init_error}"
            )
            if stream:
                async def chat_stream():
                    yield response_text
                return StreamingResponse(
                    chat_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            return JSONResponse({"response": response_text})

        # Raw diagnostic echo (REST API testing without "message" field)
        async def echo_gen():
            yield f"data: {json.dumps({'type': 'echo', 'received': data, 'invocation_id': invocation_id, 'session_id': session_id, 'init_error': _init_error})}\n\n"

        return StreamingResponse(echo_gen(), media_type="text/event-stream")

    # --- Full pipeline mode (SSE output) ---
    await _ensure_initialized()
    if _init_error:
        async def err_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': _init_error})}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    from src.models import InvocationRequest
    from src.orchestrator import run_benefits_review

    # Use catalog from request or fall back to pre-loaded file.
    # Handle wrapped catalog format {"items": [...], "catalog_version": "..."}
    # and prevent legacy flat catalogs from overriding the hardened server catalog.
    request_catalog = data.get("datapoints_catalog")
    if isinstance(request_catalog, dict) and "items" in request_catalog:
        # Unwrap wrapped catalog format
        request_catalog = request_catalog["items"]
    if request_catalog and isinstance(request_catalog, list) and len(request_catalog) > 0:
        # Only use request catalog if it has hardened fields (alignment_logic or market_mapping)
        # Otherwise prefer the server-side hardened catalog
        sample = request_catalog[0] if isinstance(request_catalog[0], dict) else {}
        has_hardened_fields = any(
            k in sample for k in ("alignment_logic", "market_mapping", "dependencies", "output_rules")
        )
        if has_hardened_fields or not _catalog_data:
            catalog_items = request_catalog
        else:
            logger.info("Ignoring legacy request catalog (%d items) — using hardened server catalog", len(request_catalog))
            catalog_items = _catalog_data
    else:
        catalog_items = _catalog_data or []

    invocation_req = InvocationRequest(
        request_id=data.get("request_id", str(uuid.uuid4())),
        country=data.get("country", "SGP"),
        company_payload=company_payload,
        market_payload=market_payload,
        datapoints_catalog=catalog_items,
    )

    if not invocation_req.market_payload:
        async def missing_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'market_payload (or market_profile) is required'})}\n\n"
        return StreamingResponse(missing_gen(), media_type="text/event-stream")

    if not invocation_req.datapoints_catalog:
        async def missing_cat_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'datapoints_catalog is required (not found in request or file)'})}\n\n"
        return StreamingResponse(missing_cat_gen(), media_type="text/event-stream")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Starting benefits review...', 'request_id': invocation_req.request_id})}\n\n"
            response = await run_benefits_review(invocation_req, _openai_client, _model)
            if response.metadata:
                for topic, ms in response.metadata.per_topic_timing.items():
                    yield f"data: {json.dumps({'type': 'topic_complete', 'topic': topic, 'time_ms': ms})}\n\n"
            result_json = response.model_dump(mode="json")
            yield f"data: {json.dumps({'type': 'done', 'result': result_json})}\n\n"
        except Exception as stream_exc:
            logger.error("Pipeline error: %s", stream_exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(stream_exc), 'error_type': type(stream_exc).__name__, 'traceback': traceback.format_exc()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    app.run()
