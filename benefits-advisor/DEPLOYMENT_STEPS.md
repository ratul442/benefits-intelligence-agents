# Benefits Advisor — Deployment Steps

This document describes how to deploy the **Benefits Cost Advisor** (Responses protocol) hosted agent to Microsoft Foundry Agent Service.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure subscription | With access to Azure AI Foundry |
| Azure CLI | v2.80+ with `az login` authenticated |
| Azure Container Registry | `<ACR_NAME>.azurecr.io` |
| Foundry Project | `<PROJECT_NAME>` on `<FOUNDRY_RESOURCE>` |
| Model deployment | `gpt-4.1-mini` (version 2025-04-14) deployed |

---

## Step 1: Build and Push the Container Image

The agent is packaged as a Docker container. Build it using Azure Container Registry (ACR) cloud build:

```bash
cd benefits-advisor

# Build for linux/amd64 and push to ACR in one step
az acr build \
  --registry <ACR_NAME> \
  --image benefits-advisor:v7 \
  --platform linux/amd64 \
  --file Dockerfile \
  --no-logs .
```

> **Note:** Use `--no-logs` on Windows to avoid encoding errors with `charmap` codec.

Get the image digest (immutable reference):
```bash
az acr repository show-manifests \
  --name <ACR_NAME> \
  --repository benefits-advisor \
  --query "[?tags[0]=='v7'].digest" -o tsv
```

---

## Step 2: Configure RBAC Permissions

### 2a. Grant AcrPull to the project's managed identity

The Foundry project's system-assigned managed identity needs permission to pull images:

```bash
# Get project managed identity
PROJECT_MI=$(az resource show \
  --ids "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.MachineLearningServices/workspaces/<PROJECT_NAME>" \
  --query "identity.principalId" -o tsv)

# Assign AcrPull
az role assignment create \
  --assignee-object-id $PROJECT_MI \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.ContainerRegistry/registries/<ACR_NAME>"
```

### 2b. Grant Foundry User to the agent identity (after creation)

After deploying, the platform creates an agent identity. Grant it **Foundry User** on the AI Services account:

```bash
# Get the agent identity principal ID from the create response
AGENT_IDENTITY="<AGENT_IDENTITY_OBJECT_ID>"

az role assignment create \
  --assignee-object-id $AGENT_IDENTITY \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<FOUNDRY_RESOURCE>"
```

### 2c. (Optional) Additional roles for model access

```bash
# Cognitive Services OpenAI User — for model inference
az role assignment create \
  --assignee-object-id $AGENT_IDENTITY \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<FOUNDRY_RESOURCE>"

# Azure AI Developer — for project-level operations
az role assignment create \
  --assignee-object-id $AGENT_IDENTITY \
  --assignee-principal-type ServicePrincipal \
  --role "Azure AI Developer" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<FOUNDRY_RESOURCE>"
```

---

## Step 3: Deploy the Agent

### Create/update the agent via REST API

```bash
# Get access token
TOKEN=$(az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv)

BASE_URL="https://<FOUNDRY_RESOURCE>.services.ai.azure.com/api/projects/<PROJECT_NAME>"
```

**Create a new agent** (POST to `/agents`):
```bash
curl -X POST "$BASE_URL/agents?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  -d '{
    "name": "benefits-advisor",
    "definition": {
      "kind": "hosted",
      "image": "<ACR_NAME>.azurecr.io/benefits-advisor@<IMAGE_DIGEST>",
      "cpu": "1",
      "memory": "2Gi",
      "container_protocol_versions": [
        {"protocol": "responses", "version": "1.0.0"}
      ],
      "environment_variables": {
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-4.1-mini",
        "TOOLBOX_NAME": "",
        "SKILL_NAMES": ""
      }
    }
  }'
```

**Create a new version** (POST to `/agents/<name>`):
```bash
curl -X POST "$BASE_URL/agents/benefits-advisor?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  -d '{
    "definition": {
      "kind": "hosted",
      "image": "<ACR_NAME>.azurecr.io/benefits-advisor@<IMAGE_DIGEST>",
      "cpu": "1",
      "memory": "2Gi",
      "container_protocol_versions": [
        {"protocol": "responses", "version": "1.0.0"}
      ],
      "environment_variables": {
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-4.1-mini",
        "TOOLBOX_NAME": "",
        "SKILL_NAMES": ""
      }
    }
  }'
```

> **Important:** Include the `Foundry-Features: HostedAgents=V1Preview` header — this is a preview feature.

---

## Step 4: Poll for Active Status

Wait until the version status is `active` before invoking:

```bash
curl -s "$BASE_URL/agents/benefits-advisor?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Foundry-Features: HostedAgents=V1Preview" | jq '.versions.latest.status'
```

Typical provisioning time: < 1 minute.

---

## Step 5: Invoke the Agent

```bash
curl -X POST "$BASE_URL/agents/benefits-advisor/endpoint/protocols/openai/responses?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Foundry-Features: HostedAgents=V1Preview" \
  -d '{
    "input": "Hello! What capabilities do you have?",
    "store": true
  }'
```

---

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Responses protocol** (not Invocations) | Multi-turn conversational; model-directed tool use; streaming support |
| **sync `DefaultAzureCredential`** | Official docs pattern; proven to work in hosted environments |
| **`server.run()`** (not `run_async`) | Matches official reference; avoids event loop race conditions |
| **`"store": False`** in agent options | Platform manages conversation history — avoids duplication |
| **Graceful skill/toolbox failure** | Skills and Toolbox failures don't crash the agent — it continues without them |

---

## Platform-Injected Environment Variables

The hosting platform automatically injects these — do NOT redeclare them in `environment_variables`:

| Variable | Purpose |
|----------|---------|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint URL |
| `FOUNDRY_PROJECT_ARM_ID` | ARM resource ID |
| `FOUNDRY_AGENT_NAME` | Agent name |
| `FOUNDRY_AGENT_VERSION` | Running version |
| `FOUNDRY_HOSTING_ENVIRONMENT` | Signals hosted mode |
| `FOUNDRY_AGENT_SESSION_ID` | Session ID per request |

---

## Custom Environment Variables

Set these in the agent definition's `environment_variables`:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name (e.g., `gpt-4.1-mini`) |
| `TOOLBOX_NAME` | No | Foundry Toolbox name for MCP tools |
| `SKILL_NAMES` | No | Comma-separated Foundry skill names |

---

## Troubleshooting

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| 500 "internal server error" (raw) | Container not ready / cold start | Wait 30s and retry |
| `"status": "failed"` in response | Container started but model call failed | Check RBAC: agent needs **Foundry User** + **Cognitive Services OpenAI User** |
| Agent version stays `creating` | Image pull failure | Verify AcrPull role on project MI |
| `preview_feature_required` error | Missing header | Add `Foundry-Features: HostedAgents=V1Preview` |
| `Agent does not exist` on POST | Wrong endpoint | Use POST `/agents/<name>` for updates, POST `/agents` for creation |

---

## Current Deployment Details

| Resource | Value |
|----------|-------|
| ACR | `<ACR_NAME>.azurecr.io` |
| Image | `benefits-advisor:v7` (`<IMAGE_DIGEST>`) |
| Foundry Endpoint | `https://<FOUNDRY_RESOURCE>.services.ai.azure.com/api/projects/<PROJECT_NAME>` |
| Agent Name | `benefits-advisor` |
| Model | `gpt-4.1-mini` |
| Protocol | Responses v1.0.0 |
| Agent Identity | `<AGENT_IDENTITY_OBJECT_ID>` |
| Blueprint Identity | `<BLUEPRINT_IDENTITY_OBJECT_ID>` |
