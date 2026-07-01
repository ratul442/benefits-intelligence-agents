# Benefits Intelligence Agents on Microsoft Foundry

> **Agentic employee-benefits benchmarking for Financial Services** — two hosted
> agents on **Microsoft Foundry** that turn benefits data and plain-language
> questions into governed cost, benchmarking, and review insights.

This repository contains **two complementary sample agents** that solve the same
business problem — **employee-benefits cost analysis and benchmarking** — using
**two different Microsoft Foundry hosted-agent protocols**. Together they show
when to use a structured, deterministic pipeline versus an interactive,
model-directed conversation.

Both are built with the **Microsoft Agent Framework** and **Azure AI Agents**
(Foundry Agent Service), and run as **hosted agents inside Foundry**.

---

## The two agents

| | [`benefits-review/`](benefits-review/) | [`benefits-advisor/`](benefits-advisor/) |
|---|---|---|
| **Protocol** | **Invocations** (fire-and-forget) | **Responses** (multi-turn, streaming) |
| **Interaction** | Single structured request → structured report | Natural multi-turn conversation |
| **What it does** | Slices a 160-datapoint benefits catalog into 9 topics, reviews them **in parallel**, validates, and returns a structured benchmarking report | Conversational cost & benchmarking advisor that uses **Foundry Toolbox** (web search + code interpreter) and **Foundry Skills** for methodology and regulatory guidance |
| **Tool use** | Deterministic, coded in the pipeline | Model-directed (decides when to search/compute) |
| **Output** | Structured JSON report | Natural language + tables + code |
| **Best for** | Batch processing, deterministic pipelines, API-to-API integration | Interactive advisory, exploratory analysis, research |

**In short:** `benefits-review` is the *structured pipeline*; `benefits-advisor`
is the *conversational analyst*. They are intentionally paired to contrast the
**Invocations** and **Responses** hosted-agent protocols on the same domain.

---

## Domain

The sample domain is **employee-benefits benchmarking** (with Singapore / SGP
sample data and regulatory context — e.g. CPF, Employment Act). All company and
market inputs are sample/synthetic; the datapoint catalog and regulatory content
are illustrative domain material, not customer data.

---

## Repository layout

```
benefits-benchmarking-agents/
├── benefits-review/     # Invocations-protocol structured benchmarking pipeline
├── benefits-advisor/    # Responses-protocol conversational advisor (Toolbox + Skills)
├── LICENSE
└── README.md            # (this file)
```

Each agent folder is self-contained with its own `README.md`, `Dockerfile`,
`requirements.txt`, `agent.yaml` / `agent.manifest.yaml`, and an `.env.example`
you fill in with your own Azure resource values.

---

## Getting started

1. Pick an agent and open its folder's `README.md`.
2. Copy `.env.example` → `.env` and fill in your own Foundry project endpoint,
   model deployment, and (where applicable) storage/toolbox/skill settings.
3. Run its local smoke test (`test_local.py`) or build and deploy it as a hosted
   Foundry agent using its `DEPLOYMENT_STEPS.md` (where provided) and
   `agent.manifest.yaml`.

> **Configuration uses placeholders** like `<FOUNDRY_RESOURCE>`,
> `<PROJECT_NAME>`, `<ACR_NAME>`, and `<IMAGE_DIGEST>`. Replace them with your own
> Azure resource values. No secrets are committed — authentication uses Managed
> Identity / `DefaultAzureCredential`.

---

## License

Released under the [MIT License](LICENSE).
