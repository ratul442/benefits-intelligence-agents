# Benefits Cost Advisor (Responses Protocol Demo)

> **Protocol:** Responses v1.0.0 | **Toolbox:** web_search + code_interpreter | **Skills:** cost-analysis-methodology, regulatory-guidance-sgp

A conversational Benefits Cost & Benchmarking Advisor that demonstrates the **Responses protocol** for hosted agents — contrasting with the Invocations protocol used by the Benefits Review agent (`../benefits-review`).

---

## Why Responses Protocol?

| Dimension | Invocations (Benefits Review) | Responses (Benefits Advisor) |
|-----------|-------------------------------|------------------------------|
| Interaction | Single structured request → response | Multi-turn natural conversation |
| Tool Use | Hardcoded in pipeline code | Model-directed (decides when to search/compute) |
| Streaming | SSE events (custom format) | Token-by-token (OpenAI-compatible) |
| State | Stateless (no memory) | Session history managed by platform |
| Input | Structured JSON payload | Natural language |
| Output | Structured JSON report | Natural language + tables + code |
| Flow Control | Developer controls orchestration | Model controls the flow |

**When to use which:**
- **Invocations**: Batch processing, structured pipelines, deterministic outputs, API-to-API integration
- **Responses**: Interactive advisory, exploratory analysis, research tasks, dynamic tool use

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Foundry Platform (Hosted)                        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ResponsesHostServer  (POST /responses)                        │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │  Agent  (gpt-4.1-mini)                                   │  │  │
│  │  │                                                          │  │  │
│  │  │  INSTRUCTIONS = SYSTEM_INSTRUCTIONS                      │  │  │
│  │  │               + cost-analysis-methodology (embedded)     │  │  │
│  │  │               + regulatory-guidance-sgp (embedded)       │  │  │
│  │  │                                                          │  │  │
│  │  │  TOOLS = [MCPStreamableHTTPTool → benefits-advisor-tools]│  │  │
│  │  │            ├── web_search                                │  │  │
│  │  │            └── code_interpreter                          │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Request Flow (Step-by-Step)

| Step | What Happens | Component |
|------|-------------|-----------|
| 1 | User sends message via Foundry Playground | Platform |
| 2 | Platform calls `POST /responses` on hosted container | ResponsesHostServer |
| 3 | Server builds prompt: instructions (with embedded skills) + conversation history + user message | Agent |
| 4 | Agent sends to `gpt-4.1-mini` | FoundryChatClient |
| 5 | Model reads `cost-analysis-methodology` and `regulatory-guidance-sgp` from system instructions | 🧠 Model knowledge |
| 6 | Model decides to call `web_search` → MCP call to Toolbox | 🔍 web_search |
| 7 | Model decides to call `code_interpreter` → MCP call to Toolbox | 🧮 code_interpreter |
| 8 | Model synthesizes final answer using search results + calculations + embedded skill frameworks | Agent |
| 9 | Response streams back to user | Platform |

### Tools vs Skills — How The Agent Accesses Each Resource

| Resource | Type | How Model Accesses It |
|----------|------|----------------------|
| `web_search` | **Tool** (via MCP Toolbox) | Model makes a function call → Toolbox executes → returns results |
| `code_interpreter` | **Tool** (via MCP Toolbox) | Model makes a function call → Toolbox executes Python → returns output |
| `cost-analysis-methodology` | **Embedded knowledge** (system prompt) | Always in context — model references directly, no call needed |
| `regulatory-guidance-sgp` | **Embedded knowledge** (system prompt) | Always in context — model references directly, no call needed |

> **Key insight:** Skills are NOT tools. They are domain knowledge (SKILL.md files) baked into the container at `/app/skills/`, read at startup by `_load_skill_content()`, and concatenated directly into the system instructions. The model always has them available — no function call required.

---

## Prerequisites

- **Azure AI Foundry project** with a deployed model (e.g., `gpt-4.1-mini`)
- **Azure CLI** logged in (`az login`)
- **Python 3.12+**
- **RBAC**: Azure AI User role on the Foundry project

---

## Setup

### 1. Install Dependencies

```bash
cd benefits-advisor
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1-mini
TOOLBOX_NAME=benefits-advisor-tools
SKILL_NAMES=cost-analysis-methodology,regulatory-guidance-sgp
```

### 3. Create Foundry Toolbox

Create a Toolbox named `benefits-advisor-tools` in the Foundry portal with:
- **web_search** tool — for market research and regulatory lookups
- **code_interpreter** tool — for cost calculations and projections

Or use the Azure SDK:
```python
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

client = AIProjectClient(
    endpoint="https://<account>.services.ai.azure.com/api/projects/<project>",
    credential=DefaultAzureCredential()
)

# Create toolbox with web_search and code_interpreter
toolbox = client.toolboxes.create(
    name="benefits-advisor-tools",
    tools=[
        {"type": "web_search", "name": "web_search"},
        {"type": "code_interpreter", "name": "code_interpreter"},
    ]
)
```

### 4. Provision Skills (One Time)

```bash
python provision_skills.py
```

Expected output:
```
Found 2 skill(s) to provision:
  - cost-analysis-methodology
  - regulatory-guidance-sgp

Provisioning skill 'cost-analysis-methodology' from skills/cost-analysis-methodology/SKILL.md...
  Imported skill 'cost-analysis-methodology' (id=skill_..., has_blob=True).

Provisioning skill 'regulatory-guidance-sgp' from skills/regulatory-guidance-sgp/SKILL.md...
  Imported skill 'regulatory-guidance-sgp' (id=skill_..., has_blob=True).

Done. Skills are ready for the agent to download at startup.
```

### 5. Run the Agent Locally

```bash
python main.py
```

Expected output:
```
INFO:__main__:Downloading skill 'cost-analysis-methodology' from Foundry...
INFO:__main__:  Unpacked skill 'cost-analysis-methodology' → downloaded_skills/cost-analysis-methodology/SKILL.md
INFO:__main__:Downloading skill 'regulatory-guidance-sgp' from Foundry...
INFO:__main__:  Unpacked skill 'regulatory-guidance-sgp' → downloaded_skills/regulatory-guidance-sgp/SKILL.md
INFO:__main__:Skills loaded: ['cost-analysis-methodology', 'regulatory-guidance-sgp']
INFO:__main__:Toolbox 'benefits-advisor-tools' connected at https://...
INFO:__main__:Benefits Cost Advisor started — Responses protocol | Model: gpt-4.1-mini | ...
```

---

## Interacting with the Agent

### Via curl

```bash
# Basic question
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What tools do you have available?"}'

# Cost analysis (triggers code_interpreter)
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Calculate total benefits cost for 500 employees with SGD 2,400/head healthcare, SGD 1,200 retirement, SGD 800 risk benefits."}'

# Regulatory question (triggers skills)
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What are the current CPF contribution rates in Singapore for employees under 55?"}'

# Market research (triggers web_search)
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Search for latest Singapore employee benefits trends in 2026."}'
```

### Via PowerShell

```powershell
# Basic question
Invoke-WebRequest -Uri "http://localhost:8088/responses" -Method POST `
  -ContentType "application/json" `
  -Body '{"input": "What tools do you have available?"}'

# Cost calculation
$body = @{input = "Calculate benefits cost for 500 employees: healthcare SGD 2400, retirement SGD 1200, risk SGD 800 per employee."} | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:8088/responses" -Method POST -ContentType "application/json" -Body $body
```

### Via Agent Inspector (VS Code)

Open Command Palette → `Foundry Toolkit: Open Agent Inspector` → send messages interactively.

### Via Test Script

```bash
python test_local.py
```

---

## Demo Conversation Flows (Copy-Paste Ready)

> **Legend:** 🧮 = `code_interpreter` | 🔍 = `web_search` | 📘 = `cost-analysis-methodology` | 📜 = `regulatory-guidance-sgp` | 🧠 = Model knowledge

Copy each message into the agent chat in order. Each flow is a complete end-to-end demo.

---

### Flow 1: Cost Analysis & Benchmarking

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| 1 | What's the total annual benefits cost for 500 employees at SGD 5,400 per head? | 🧮 code_interpreter |
| 2 | Break down our benefits spend into healthcare, retirement, and risk categories and compare to market benchmarks. | 🧮 code_interpreter + 📘 cost-analysis-methodology |
| 3 | Compare our per-employee benefits cost of SGD 5,400 against the 25th, 50th, and 75th market percentiles. | 🧮 code_interpreter + 🔍 web_search + 📘 cost-analysis-methodology |
| 4 | Project our benefits costs forward 3 years assuming 5% medical inflation and 3% headcount growth. | 🧮 code_interpreter + 📘 cost-analysis-methodology |
| 5 | Now model 3 scenarios — lean, median, and premium — with full cost breakdowns for each. | 🧮 code_interpreter + 📘 cost-analysis-methodology |
| 6 | Suggest ways to reduce our total benefits cost by 10% without cutting coverage. | 📘 cost-analysis-methodology + 🧮 code_interpreter |

---

### Flow 2: Regulatory & CPF Deep-Dive

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| 1 | What are the current CPF contribution rates for employees under 55 in Singapore? | 📜 regulatory-guidance-sgp |
| 2 | Search the web for any CPF rate changes announced for 2025 or 2026. | 🔍 web_search + 📜 regulatory-guidance-sgp |
| 3 | Can we reduce employer CPF contributions below the statutory minimum? What are the penalties? | 📜 regulatory-guidance-sgp |
| 4 | Calculate the total CPF cost for 500 employees with average salary SGD 8,000/month across all age tiers (90% under 55, 7% age 55-60, 3% age 60-65). | 🧮 code_interpreter + 📜 regulatory-guidance-sgp |
| 5 | What are the Employment Act requirements for annual leave and sick leave in Singapore? | 📜 regulatory-guidance-sgp |
| 6 | Are there tax-advantaged benefit structures available in Singapore? Search for recent IRAS guidelines. | 📜 regulatory-guidance-sgp + 🔍 web_search |

---

### Flow 3: Market Research & Trends

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| 1 | What are the latest employee benefits trends in Singapore for 2026? | 🔍 web_search |
| 2 | Search for benchmarking data on healthcare costs in the APAC region. | 🔍 web_search |
| 3 | What are competitors in Singapore's financial services sector offering for employee wellness? | 🔍 web_search |
| 4 | What percentage of salary should we budget for employee benefits in Singapore? | 🔍 web_search + 📘 cost-analysis-methodology |
| 5 | What's the average employer contribution to group health insurance in Singapore? | 🔍 web_search + 📘 cost-analysis-methodology |
| 6 | Compare Singapore benefits costs to Hong Kong and Australia for 500 employees. | 🔍 web_search + 🧮 code_interpreter |

---

### Flow 4: Benefits Optimization Strategy

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| 1 | We have 800 employees in Singapore, financial services sector, average salary SGD 8,500/month. Current benefits spend is SGD 5,400 per employee annually. Benchmark us. | 🧮 code_interpreter + 🔍 web_search + 📘 cost-analysis-methodology |
| 2 | What would be the savings if we switch from a defined benefit to a flexible benefits model? | 🧮 code_interpreter + 📘 cost-analysis-methodology + 🔍 web_search |
| 3 | Model the cost difference between full-time employees and contract workers for benefits. | 🧮 code_interpreter + 📜 regulatory-guidance-sgp |
| 4 | What are the trade-offs between self-insured and fully-insured health plans? | 🔍 web_search + 📘 cost-analysis-methodology |
| 5 | Recommend a redesigned benefits package that reduces cost by 15% while maintaining competitive positioning. | 📘 cost-analysis-methodology + 🧮 code_interpreter + 📜 regulatory-guidance-sgp |
| 6 | Create a 5-year projection of the optimized plan with 6% medical inflation and 2% headcount growth. | 🧮 code_interpreter + 📘 cost-analysis-methodology |

---

### Flow 5: New Company / Startup Benefits Design

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| 1 | Recommend a benefits structure for a startup with 50 employees and a SGD 250,000 annual budget in Singapore. | 🧮 code_interpreter + 📘 cost-analysis-methodology + 📜 regulatory-guidance-sgp |
| 2 | What are the mandatory statutory benefits we must provide under Singapore law? | 📜 regulatory-guidance-sgp |
| 3 | After covering mandatory CPF and leave, how much budget remains for discretionary benefits? Calculate it. | 🧮 code_interpreter + 📜 regulatory-guidance-sgp |
| 4 | Search for what tech startups in Singapore typically offer for employee wellness and flexible benefits. | 🔍 web_search |
| 5 | Design a competitive package that fits within our remaining budget and includes healthcare, wellness allowance, and flexible benefits. | 🧮 code_interpreter + 📘 cost-analysis-methodology |
| 6 | Project how this package scales as we grow to 200 employees over 3 years. | 🧮 code_interpreter + 📘 cost-analysis-methodology |

---

### Flow 6: Quick Single-Turn Questions (No Follow-Up Needed)

| # | Message (copy-paste this) | Tools Used |
|---|---------------------------|-----------|
| — | What's the OW ceiling for CPF in 2025? | 📜 regulatory-guidance-sgp |
| — | What are the 6 cost decomposition categories in the benefits cost analysis methodology? | 📘 cost-analysis-methodology |
| — | Search for Mercer Singapore benefits survey 2026. | 🔍 web_search |
| — | Calculate total employer cost for an employee earning SGD 10,000/month including CPF. | 🧮 code_interpreter + 📜 regulatory-guidance-sgp |
| — | Explain the MOM guidelines on flexible work arrangements and their cost implications. | 📜 regulatory-guidance-sgp + 🔍 web_search |
| — | What's the difference between the Responses protocol and Invocations protocol for this agent? | 🧠 Model knowledge |

---

## Input Data for Best Results

The agent will proceed with Singapore market defaults if you don't provide specifics, but you'll get more accurate analysis if you include the following in your message:

| Data Point | Why It Helps | Default If Not Provided |
|------------|-------------|------------------------|
| **Number of employees** | Scale calculations, tier thresholds | 500 employees |
| **Average salary (SGD/month or annual)** | Benefits-as-%-of-salary ratios | SGD 6,000/month (SGD 72,000/year) |
| **Annual benefits spend per head (SGD)** | Benchmarking against market percentiles | SGD 5,400/head |
| **Industry sector** | Sector-specific benchmarks (FSI, tech, manufacturing) | Financial services |
| **Benefits categories & spend breakdown** | Per-category comparison (healthcare, retirement, risk, time-off, perks, admin) | Equal distribution across 6 categories |
| **Employee age profile** | CPF rate tiers (under 55, 55–60, 60–65, 65–70, 70+) | 100% under 55 |
| **Projection horizon (years)** | Forward-looking cost models | 3 years |
| **Inflation / growth assumptions** | Multi-year projections | 5% medical inflation, 3% headcount growth |

### Example — Fully Specified Request

> "We have 800 employees in Singapore, average salary SGD 8,500/month, financial services sector. Current benefits spend: healthcare SGD 2,800, retirement SGD 1,400, risk SGD 600 per employee annually. 90% are under 55, 10% are 55-60. Project costs for 5 years with 6% medical inflation and 2% headcount growth, and benchmark against market."

### Example — Minimal Request (agent uses defaults)

> "Break down our benefits spend and compare to market benchmarks."

The agent will assume Singapore market norms and state all assumptions in its response.

---

## Deploying to Foundry

The agent is packaged as a Docker container and deployed as a **hosted Foundry
agent** using the **Responses** protocol. The complete, copy-pasteable guide —
prerequisites, image build, RBAC, registration via REST, and invocation — is in
[`DEPLOYMENT_STEPS.md`](DEPLOYMENT_STEPS.md). The summary below covers the main paths.

**Prerequisites:** an Azure subscription with Azure AI Foundry, Azure CLI (`az login`),
an Azure Container Registry, a Foundry project, and a `gpt-4.1-mini` model deployment.
If you use Skills/Toolbox, provision the skills first with `python provision_skills.py`.

### Recommended: az acr build + register (REST)

```bash
cd benefits-advisor

# 1. Build & push the image to ACR (cloud build — no local Docker needed)
az acr build --registry <ACR_NAME> --image benefits-advisor:v1 \
  --platform linux/amd64 --file Dockerfile --no-logs .

# 2. Get the immutable digest
az acr repository show-manifests --name <ACR_NAME> --repository benefits-advisor \
  --query "[?tags[0]=='v1'].digest" -o tsv
```

Then grant RBAC (`AcrPull` to the project MI; **Foundry User** +
**Cognitive Services OpenAI User** to the agent identity) and register the agent
version via `POST /agents` (declaring the `responses` protocol and the image
digest). Full commands and request bodies are in
[`DEPLOYMENT_STEPS.md`](DEPLOYMENT_STEPS.md).

> The platform injects `FOUNDRY_PROJECT_ENDPOINT` and other `FOUNDRY_*` variables —
> do not declare them in `environment_variables`. Authentication uses Managed
> Identity; no secrets are committed.

### Alternative: Azure Developer CLI (azd)

```bash
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "gpt-4.1-mini"
azd env set TOOLBOX_NAME "benefits-advisor-tools"
azd env set SKILL_NAMES "cost-analysis-methodology,regulatory-guidance-sgp"

azd ai agent init -m agent.manifest.yaml
azd up
```

### Alternative: Foundry Toolkit VS Code Extension

1. Command Palette → `Foundry Toolkit: Deploy Hosted Agent`
2. Select deployment method (Code or Container)
3. Configure environment variables
4. Deploy

---

## File Structure

```
benefits-advisor/
├── main.py                      # Agent entry point (Responses protocol)
├── provision_skills.py          # One-time skill upload to Foundry
├── test_local.py                # Local testing script
├── agent.manifest.yaml          # Foundry agent manifest (declares protocol, tools, skills)
├── agent.yaml                   # Container agent config
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container image definition
├── .env.example                 # Environment variable template
├── .gitignore
├── .dockerignore
├── README.md                    # This file
└── skills/                      # Skill source files (input to provision_skills.py)
    ├── cost-analysis-methodology/
    │   └── SKILL.md             # Cost analysis framework and methodology
    └── regulatory-guidance-sgp/
        └── SKILL.md             # Singapore CPF, Employment Act, MOM guidelines
```

---

## Comparison with Benefits Review Agent

| Aspect | Benefits Review (Invocations) | Benefits Advisor (Responses) |
|--------|-------------------------------|------------------------------|
| Entry point | `InvocationAgentServerHost` | `ResponsesHostServer` |
| Endpoint | `POST /invocations` | `POST /responses` |
| Input format | `{"company_payload": "...", "market_payload": "..."}` | `{"input": "natural language"}` |
| Tool invocation | Hardcoded pipeline (topic_slicer → prompt_builder → LLM → alignment) | Model decides: web_search, code_interpreter, load_skill |
| Output format | Structured JSON (160 ReportRows) | Natural language + tables |
| Multi-turn | No (stateless) | Yes (platform manages sessions) |
| Streaming | Custom SSE events | OpenAI-compatible streaming |
| Best for | Automated batch processing | Interactive advisory |

---

## Updating Skills

To update a skill after editing its `SKILL.md`:

```bash
# Re-run provisioning (deletes old version, uploads new)
python provision_skills.py

# Restart the agent to pick up the new version
# (agent downloads fresh copies on every boot)
python main.py
```

No code changes or container rebuild needed — behavioral updates are decoupled from code.
