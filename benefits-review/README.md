# Benefits Review Agent

AI-assisted benefits benchmarking sample that demonstrates the Microsoft Foundry hosted-agent **Invocations protocol**. It accepts structured company and market payloads, slices a 160-datapoint benefits catalog into nine benefit topics, runs the topic reviews in parallel, validates the outputs, and returns a structured benchmarking report.

## Architecture

The `src/` package is organized around a deterministic review pipeline:

- `main.py` exposes the hosted invocation endpoint.
- `orchestrator.py` coordinates the end-to-end multi-topic review.
- `topic_slicer.py` maps catalog datapoints to topic-specific work items.
- `prompt_builder.py` builds topic prompts with the relevant company, market, and catalog context.
- `output_parser.py` parses model responses into structured report sections.
- `validators.py` applies schema and quality checks.
- `alignment.py` normalizes and aligns output to the catalog and reporting requirements.
- `models.py` defines shared request and response models.

The catalog lives in `data/catalog/datapoints_catalog.json` and keeps the employee-benefits domain content, including Singapore sample datapoints and regulatory context.

## Configure

Copy `.env.example` to `.env` and fill in your Foundry project and model deployment values:

```powershell
Copy-Item .env.example .env
```

No real Azure identifiers are included in this sample. Hosted deployments can inject `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and observability settings through the platform.

## Run locally

Install dependencies, then run the local smoke test:

```powershell
pip install -r requirements.txt
python test_local.py
```

`test_local.py` exercises the pipeline locally with sample input. It is intended for validation before packaging the hosted agent.

## Deploy to Microsoft Foundry

The agent is packaged as a Docker container and deployed as a **hosted Foundry
agent** using the **Invocations** protocol. The full, copy-pasteable guide —
including RBAC, registration, and invocation — is in
[`DEPLOYMENT_STEPS.md`](DEPLOYMENT_STEPS.md). The short version:

**Prerequisites:** an Azure subscription with Azure AI Foundry, Azure CLI (`az login`),
an Azure Container Registry, a Foundry project, and a chat model deployment
(e.g. `gpt-5.4`).

1. **Build & push the image** to ACR (cloud build — no local Docker needed):
   ```bash
   cd benefits-review
   az acr build --registry <ACR_NAME> --image benefits-review:v1 \
     --platform linux/amd64 --file Dockerfile --no-logs .
   ```
2. **Grant RBAC** — `AcrPull` to the project managed identity, and (after the
   agent identity exists) **Foundry User** + **Cognitive Services OpenAI User** to
   the agent identity. See [`DEPLOYMENT_STEPS.md`](DEPLOYMENT_STEPS.md) Step 2.
3. **Register the agent version** via the Foundry REST API (`POST /agents`, then
   `POST /agents/benefits-review` for updates), pointing at the image digest and
   declaring the `invocations` protocol. See Step 3.
4. **Poll for `active` status**, then **invoke** at
   `/agents/benefits-review/endpoint/protocols/invocations?api-version=v1`.

> The platform injects `FOUNDRY_PROJECT_ENDPOINT` and
> `APPLICATIONINSIGHTS_CONNECTION_STRING` — do not declare them in the agent's
> `environment_variables`. Authentication uses Managed Identity; no secrets are
> committed.

Deployment manifests (`agent.yaml`, `agent.manifest.yaml`) are included for
`azd`/toolkit-based flows as an alternative to the manual REST steps above.
