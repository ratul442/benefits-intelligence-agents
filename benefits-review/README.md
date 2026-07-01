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
