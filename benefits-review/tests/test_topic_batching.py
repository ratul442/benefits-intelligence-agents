"""Regression tests for bounded topic batching and omission retries."""

import asyncio
import json
import unittest
from types import SimpleNamespace

from src.models import DatapointEntry, InvocationRequest, TopicSlice
from src.orchestrator import (
    _model_request_parameters,
    _process_single_topic,
    run_benefits_review,
)
from src.topic_slicer import MAX_DATAPOINTS_PER_BATCH, slice_payloads


def _datapoint(index: int) -> DatapointEntry:
    return DatapointEntry(
        comparison_key=f"health_{index}",
        pretty_name=f"Health {index}",
        benefit_topic="Healthcare",
        company_prompt=f"Extract health datapoint {index}.",
    )


def _response_rows(keys: list[str]):
    rows = [
        {
            "comparison_key": key,
            "pretty_name": key,
            "company_provision": "Company fact",
            "market_practice": "Market fact",
            "market_alignment": "= Broadly Aligned",
        }
        for key in keys
    ]
    return SimpleNamespace(
        output_text=json.dumps({"rows": rows}),
        usage=SimpleNamespace(
            input_tokens=70,
            output_tokens=30,
            total_tokens=100,
        ),
    )


class _Responses:
    def __init__(self, outputs, delay=0):
        self.outputs = iter(outputs)
        self.calls = []
        self.delay = delay

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        output = next(self.outputs)
        if self.delay:
            await asyncio.sleep(self.delay)
        return output


class TopicBatchingTests(unittest.TestCase):
    def test_large_topic_uses_complete_source_in_batches_of_15(self):
        catalog = [_datapoint(index) for index in range(47)]
        company = "## Healthcare\n\nComplete company healthcare section"
        market = "## Healthcare\n\nComplete market healthcare section"

        slices = slice_payloads(company, market, catalog)

        self.assertEqual(MAX_DATAPOINTS_PER_BATCH, 15)
        self.assertEqual([len(item.datapoints) for item in slices], [15, 15, 15, 2])
        self.assertEqual([item.batch_index for item in slices], [1, 2, 3, 4])
        self.assertTrue(all(item.batch_count == 4 for item in slices))
        self.assertTrue(all(item.company_slice == slices[0].company_slice for item in slices))
        self.assertTrue(all(item.market_slice == slices[0].market_slice for item in slices))
        self.assertEqual(
            [dp.comparison_key for item in slices for dp in item.datapoints],
            [dp.comparison_key for dp in catalog],
        )

    def test_gpt5_terra_uses_reasoning_without_sampling_parameters(self):
        parameters = _model_request_parameters("gpt-5.6-terra")

        self.assertEqual(parameters, {"reasoning": {"effort": "low"}})
        self.assertNotIn("temperature", parameters)
        self.assertNotIn("top_p", parameters)

    def test_gpt41_keeps_temperature_without_reasoning(self):
        parameters = _model_request_parameters("gpt-4.1")

        self.assertEqual(parameters["temperature"], 0.0)
        self.assertNotIn("reasoning", parameters)


class TopicRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_omitted_key_is_retried_and_recovered(self):
        datapoints = [_datapoint(index) for index in range(3)]
        responses = _Responses([
            _response_rows(["health_0", "health_2"]),
            _response_rows(["health_1"]),
        ])
        client = SimpleNamespace(responses=responses)
        topic_slice = TopicSlice(
            topic_name="Healthcare",
            company_slice="## Healthcare\n\nComplete company section",
            market_slice="## Healthcare\n\nComplete market section",
            datapoints=datapoints,
        )

        result = await _process_single_topic(client, topic_slice, "test-model", "SGP")

        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(result.initially_missing_keys, ["health_1"])
        self.assertEqual(result.recovered_keys, ["health_1"])
        self.assertEqual(result.model_omitted_keys, ["health_1"])
        self.assertEqual(result.parser_dropped_keys, [])
        self.assertEqual(result.input_tokens, 140)
        self.assertEqual(result.output_tokens, 60)
        self.assertEqual(result.token_usage, 200)
        self.assertTrue(result.started_at)
        self.assertTrue(result.ended_at)
        self.assertGreaterEqual(result.retry_time_ms, 0)
        self.assertEqual(
            {row.comparison_key for row in result.rows},
            {"health_0", "health_1", "health_2"},
        )
        retry_input = responses.calls[1]["input"][0]["content"]
        self.assertIn("health_1", retry_input)
        self.assertNotIn("health_0", retry_input)
        self.assertIn("Complete company section", retry_input)
        self.assertIn("Complete market section", retry_input)

    async def test_pipeline_publishes_rows_and_execution_telemetry(self):
        datapoints = [_datapoint(index) for index in range(16)]
        responses = _Responses(
            [
                _response_rows([f"health_{index}" for index in range(15)]),
                _response_rows(["health_15"]),
            ],
            delay=0.01,
        )
        client = SimpleNamespace(responses=responses)
        request = InvocationRequest(
            request_id="telemetry-test",
            country="SGP",
            company_payload="## Healthcare\n\nComplete company section",
            market_payload="## Healthcare\n\nComplete market section",
            datapoints_catalog=datapoints,
        )
        events = []

        async def capture(event):
            events.append(event)

        response = await run_benefits_review(
            request,
            client,
            model="test-model",
            event_callback=capture,
        )

        self.assertEqual(response.status, "completed")
        self.assertEqual([event["type"] for event in events].count("row"), 16)
        self.assertTrue(all(
            event["provisional"] for event in events if event["type"] == "row"
        ))
        self.assertEqual(response.metadata.streamed_rows, 16)
        self.assertIsNotNone(response.metadata.time_to_first_row_ms)
        self.assertEqual(response.metadata.peak_concurrency, 2)
        self.assertEqual(len(response.metadata.batch_telemetry), 2)
        batch = response.metadata.batch_telemetry[0]
        self.assertEqual(batch.input_tokens, 70)
        self.assertEqual(batch.output_tokens, 30)
        self.assertEqual(batch.total_tokens, 100)
        self.assertEqual(batch.extraction_input_tokens, 70)
        self.assertEqual(batch.extraction_output_tokens, 30)
        self.assertEqual(batch.retry_input_tokens, 0)
        self.assertEqual(batch.audit_input_tokens, 0)
        self.assertGreaterEqual(batch.extraction_llm_time_ms, 0)
        self.assertTrue(batch.started_at)
        self.assertTrue(batch.ended_at)
        self.assertEqual(
            {event.event for event in response.metadata.concurrency_timeline},
            {"queued", "started", "finished"},
        )


if __name__ == "__main__":
    unittest.main()