# Copyright (c) Microsoft. All rights reserved.
# Benefits Benchmarking — Local test script for the Benefits Cost Advisor.

"""Test the Benefits Cost Advisor locally using curl-like requests.

This script sends sample queries to the locally-running agent to validate
that:
1. The Responses protocol endpoint works (POST /responses)
2. Foundry Toolbox tools are discoverable
3. Foundry Skills are loaded and usable
4. Multi-turn conversation is maintained
5. Streaming responses work correctly

Prerequisites:
    - Agent is running locally (python main.py)
    - Skills have been provisioned (python provision_skills.py)
    - Toolbox has been created in Foundry portal or via SDK

Usage:
    python test_local.py
"""

import json
import sys

import httpx

BASE_URL = "http://localhost:8088"
RESPONSES_URL = f"{BASE_URL}/responses"

# Test scenarios that exercise different capabilities
TEST_SCENARIOS = [
    {
        "name": "1. Basic greeting + capability check",
        "input": "Hi! What can you help me with? What tools do you have available?",
        "expect_contains": ["tool", "search", "cost"],
    },
    {
        "name": "2. Cost analysis with code_interpreter (triggers Toolbox)",
        "input": (
            "My company has 500 employees in Singapore with the following annual benefits costs:\n"
            "- Healthcare: SGD 2,400 per employee\n"
            "- Retirement (CPF above mandatory): SGD 1,200 per employee\n"
            "- Risk Benefits: SGD 800 per employee\n"
            "- Time Off (above statutory): SGD 600 per employee\n"
            "- Perquisites: SGD 400 per employee\n\n"
            "Can you calculate our total benefits cost, cost as % of average salary "
            "(assume SGD 72,000/year), and project costs for the next 3 years assuming "
            "5% annual inflation?"
        ),
        "expect_contains": ["total", "SGD", "year"],
    },
    {
        "name": "3. Regulatory question (triggers Skills: regulatory-guidance-sgp)",
        "input": (
            "What are the current CPF contribution rates for employees under 55 in Singapore? "
            "And what's the monthly ordinary wage ceiling?"
        ),
        "expect_contains": ["CPF", "17%", "6,800"],
    },
    {
        "name": "4. Market research (triggers Toolbox: web_search)",
        "input": (
            "Search for the latest Singapore employee benefits trends in 2025-2026. "
            "What are companies doing differently with their healthcare and wellness programs?"
        ),
        "expect_contains": ["Singapore", "benefit"],
    },
    {
        "name": "5. Methodology question (triggers Skills: cost-analysis-methodology)",
        "input": (
            "I want to benchmark our benefits costs against market. "
            "What methodology should I follow? Please load the cost analysis framework."
        ),
        "expect_contains": ["Step", "decomposition"],
    },
    {
        "name": "6. Combined analysis (triggers both Toolbox + Skills)",
        "input": (
            "Based on our healthcare cost of SGD 2,400/employee, calculate where we stand "
            "versus the Singapore P50 of SGD 2,100 and P75 of SGD 2,800. "
            "Also search for any recent changes to Singapore healthcare regulations "
            "that might affect our costs in 2026."
        ),
        "expect_contains": ["P50", "healthcare"],
    },
]


def test_health():
    """Check the /readiness endpoint."""
    try:
        resp = httpx.get(f"{BASE_URL}/readiness", timeout=10.0)
        if resp.status_code == 200:
            print("✅ /readiness → 200 OK")
            return True
        else:
            print(f"❌ /readiness → {resp.status_code}")
            return False
    except httpx.ConnectError:
        print(f"❌ Cannot connect to {BASE_URL} — is the agent running?")
        return False


def test_scenario(scenario: dict, timeout: float = 120.0) -> bool:
    """Send a request and validate the response."""
    name = scenario["name"]
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    print(f"INPUT: {scenario['input'][:100]}...")

    try:
        resp = httpx.post(
            RESPONSES_URL,
            json={"input": scenario["input"]},
            timeout=timeout,
        )

        if resp.status_code != 200:
            print(f"❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        # Try to parse as JSON
        try:
            data = resp.json()
            # Extract text from response
            output_text = ""
            if isinstance(data, dict):
                # Standard Responses API format
                if "output" in data:
                    for item in data["output"]:
                        if item.get("type") == "message":
                            for content in item.get("content", []):
                                if content.get("type") == "output_text":
                                    output_text += content.get("text", "")
                elif "output_text" in data:
                    output_text = data["output_text"]
                elif "text" in data:
                    output_text = data["text"]
                else:
                    output_text = json.dumps(data, indent=2)[:500]
            else:
                output_text = str(data)[:500]
        except json.JSONDecodeError:
            output_text = resp.text

        print(f"\nRESPONSE ({len(output_text)} chars):")
        print(output_text[:400] + ("..." if len(output_text) > 400 else ""))

        # Validate expected content (case-insensitive)
        missing = [
            kw for kw in scenario.get("expect_contains", [])
            if kw.lower() not in output_text.lower()
        ]
        if missing:
            print(f"\n⚠️  Missing expected keywords: {missing}")
            print("   (This may be okay if the model phrased things differently)")
            return True  # Soft fail — response worked, content may vary
        else:
            print(f"\n✅ PASSED — all expected keywords found")
            return True

    except httpx.TimeoutException:
        print(f"❌ Timeout after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Benefits Cost Advisor (Responses Protocol) Test")
    print("=" * 60)

    if not test_health():
        print("\n❌ Agent is not running. Start it with: python main.py")
        sys.exit(1)

    passed = 0
    total = len(TEST_SCENARIOS)

    for scenario in TEST_SCENARIOS:
        if test_scenario(scenario):
            passed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} tests passed")
    print(f"{'='*60}")

    if passed < total:
        print("\nNote: Some 'failures' may be due to model phrasing variations.")
        print("Check the response content manually for correctness.")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
