# Benefits Review Agent — Deployment Steps

This document describes how to deploy the **Benefits Review Agent** (Invocations
protocol) as a hosted agent on Microsoft Foundry Agent Service.

> The Benefits Review agent is a **structured pipeline**: one JSON request in
> (company + market payloads + a datapoints catalog), one structured benchmarking
> report out. It uses the **Invocations** protocol. For the conversational
> counterpart, see [`../benefits-advisor`](../benefits-advisor) (Responses protocol).

All resource-specific values are placeholders — replace them with your own:
`<ACR_NAME>`, `<FOUNDRY_RESOURCE>`, `<PROJECT_NAME>`, `<SUBSCRIPTION_ID>`,
`<RESOURCE_GROUP>`, `<IMAGE_DIGEST>`, `<AGENT_IDENTITY_OBJECT_ID>`.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure subscription | With access to Azure AI Foundry |
| Azure CLI | v2.80+, authenticated with `az login` |
| Azure Container Registry | `<ACR_NAME>.azurecr.io` |
| Foundry Project | `<PROJECT_NAME>` on `<FOUNDRY_RESOURCE>` |
| Model deployment | A chat model deployed in the project (e.g. `gpt-5.4`) |
| `jq` | For parsing JSON responses (optional but handy) |

---

## Step 1: Build and Push the Container Image

The agent is packaged as a Docker container. Build it with Azure Container
Registry (ACR) cloud build so you don't need a local Docker daemon:

```bash
cd benefits-review

# Build for linux/amd64 and push to ACR in one step
az acr build \
  --registry <ACR_NAME> \
  --image benefits-review:v1 \
  --platform linux/amd64 \
  --file Dockerfile \
  --no-logs .
```

> **Windows note:** `--no-logs` avoids `charmap` codec errors when streaming build
> logs. If the log stream crashes, the build still runs — verify with
> `az acr task list-runs --registry <ACR_NAME> --output table`.

Get the immutable image digest:

```bash
az acr repository show-manifests \
  --name <ACR_NAME> \
  --repository benefits-review \
  --query "[?tags[0]=='v1'].digest" -o tsv
```

Use the returned `sha256:...` value as `<IMAGE_DIGEST>` below.

---

## Step 2: Configure RBAC Permissions

### 2a. Grant AcrPull to the project's managed identity

The Foundry project's managed identity needs permission to pull the image:

```bash
# Get the project managed identity principal ID
PROJECT_MI=$(az resource show \
  --ids "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.MachineLearningServices/workspaces/<PROJECT_NAME>" \
  --query "identity.principalId" -o tsv)

az role assignment create \
  --assignee-object-id $PROJECT_MI \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.ContainerRegistry/registries/<ACR_NAME>"
```

### 2b. Grant data-plane roles to the agent identity (after creation)

After the agent version is created, the platform provisions an **agent identity**.
Grant it the roles it needs on the AI Services (Foundry) account. Data-plane role
assignments must target the **agent instance identity**, not the project MI:

```bash
AGENT_IDENTITY="<AGENT_IDENTITY_OBJECT_ID>"
ACCOUNT_SCOPE="/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<FOUNDRY_RESOURCE>"

# Foundry User — hosted-agent data plane (role GUID 53ca6127... is the public built-in id)
az role assignment create \
  --assignee-object-id $AGENT_IDENTITY --assignee-principal-type ServicePrincipal \
  --role 53ca6127-db72-4b80-b1b0-d745d6d5456d --scope "$ACCOUNT_SCOPE"

# Cognitive Services OpenAI User — for model inference
az role assignment create \
  --assignee-object-id $AGENT_IDENTITY --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" --scope "$ACCOUNT_SCOPE"
```

> RBAC can take **5–10 minutes** to propagate. If early invocations return
> permission errors, wait and retry.

---

## Step 3: Register / Update the Agent

```bash
# Get an access token
TOKEN=$(az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv)
BASE_URL="https://<FOUNDRY_RESOURCE>.services.ai.azure.com/api/projects/<PROJECT_NAME>"
```

**Create the agent** (first time — POST to `/agents`):

```bash
curl -X POST "$BASE_URL/agents?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  -d '{
    "name": "benefits-review",
    "definition": {
      "kind": "hosted",
      "image": "<ACR_NAME>.azurecr.io/benefits-review@<IMAGE_DIGEST>",
      "cpu": "1",
      "memory": "2Gi",
      "container_protocol_versions": [
        {"protocol": "invocations", "version": "1.0.0"}
      ],
      "environment_variables": {
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-5.4",
        "CONTAINER_TAG": "v1",
        "PROMPT_VERSION": "2026-05-sgp-v1"
      }
    }
  }'
```

**Deploy a new version** (subsequent updates — POST to `/agents/benefits-review`):
use the same body's `definition` block with the new `<IMAGE_DIGEST>` and a bumped
`CONTAINER_TAG`.

> **Important:** Include the `Foundry-Features: HostedAgents=V1Preview` header — it
> is a preview feature. Do **not** declare `FOUNDRY_PROJECT_ENDPOINT` or
> `APPLICATIONINSIGHTS_CONNECTION_STRING` in `environment_variables` — the platform
> injects them automatically.

---

## Step 4: Poll for Active Status

Wait until the latest version is `active` before invoking:

```bash
curl -s "$BASE_URL/agents/benefits-review?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Foundry-Features: HostedAgents=V1Preview" | jq '.versions.latest.status'
```

Typical provisioning time: about a minute.

---

## Step 5: Invoke the Agent

```bash
curl -X POST "$BASE_URL/agents/benefits-review/endpoint/protocols/invocations?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  -d '{
    "input": {
      "request_id": "demo-001",
      "country": "SGP",
      "company_payload": "<company markdown>",
      "market_payload": "<market markdown>",
      "datapoints_catalog": []
    }
  }'
```

The response is an SSE stream ending in a `done` event whose `result` is the
structured Benefits Review report. See `test_local.py` for a runnable example of
building the request payload.

---

## Environment Variables

**Platform-injected** (do NOT declare these in `environment_variables`):

| Variable | Purpose |
|----------|---------|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint URL |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Observability (if enabled) |
| `FOUNDRY_AGENT_VERSION` | Running version |

**Set in the agent definition** (see `.env.example` for local values):

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Chat model deployment name (e.g. `gpt-5.4`) |
| `AZURE_OPENAI_ENDPOINT` | Local only | Azure OpenAI endpoint (hosted uses the project endpoint) |
| `AZURE_OPENAI_API_VERSION` | Local only | API version for local runs |
| `CONTAINER_TAG` | Recommended | Traceability tag matching the image tag |
| `PROMPT_VERSION` | Optional | Prompt/catalog version for traceability |
| `ENABLE_INSTRUMENTATION` | Optional | `true`/`false` — OpenTelemetry tracing |

---

## Troubleshooting

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Agent version stays `creating` | Image pull failure | Verify **AcrPull** on the project MI (Step 2a) |
| `"status": "failed"` after invoke | Model call denied | Grant **Foundry User** + **Cognitive Services OpenAI User** to the agent identity (Step 2b); wait 5–10 min |
| `preview_feature_required` | Missing header | Add `Foundry-Features: HostedAgents=V1Preview` |
| `Agent does not exist` on POST | Wrong endpoint | POST `/agents` to create, POST `/agents/<name>` to add a version |
| `az acr build` log stream crashes (Windows) | cp1252 codec | Cosmetic — verify via `az acr task list-runs` |
