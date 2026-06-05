from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.rag_report.report_vnext import llm


class TestReportVNextLLM(unittest.TestCase):
    def test_task_model_config_uses_expected_provider_defaults(self) -> None:
        extraction = llm.get_task_model_config("extraction")
        reasoning = llm.get_task_model_config("financial_reasoning")
        chart = llm.get_task_model_config("chart_planning")

        self.assertEqual(extraction.model, "gemini-2.5-flash")
        self.assertEqual(extraction.base_url, "https://direct.shopaikey.com/v1")
        self.assertEqual(reasoning.model, "qwen3-235b-a22b-thinking-2507")
        self.assertEqual(reasoning.base_url, "https://api.shopaikey.com/v1")
        self.assertEqual(chart.model, "qwen3-235b-a22b-thinking-2507")
        self.assertEqual(chart.base_url, "https://api.shopaikey.com/v1")

    @patch("src.rag_report.report_vnext.llm.OpenAI")
    def test_get_llm_client_does_not_pass_timeout(self, openai_cls: Mock) -> None:
        openai_cls.return_value = Mock()
        with patch("src.rag_report.report_vnext.llm.settings.EXTRACTION_API_KEY", "token"):
            client, _ = llm.get_llm_client("extraction")
        self.assertIs(client, openai_cls.return_value)
        self.assertEqual(
            openai_cls.call_args.kwargs,
            {"api_key": "token", "base_url": "https://direct.shopaikey.com/v1"},
        )

    def test_call_llm_until_nonempty_retries_on_empty_stream_output(self) -> None:
        empty_stream = []
        chunk = Mock()
        choice = Mock()
        choice.delta = Mock(content=[Mock(text="ok")])
        choice.finish_reason = "stop"
        chunk.choices = [choice]
        success_stream = [chunk]
        create = Mock(side_effect=[empty_stream, success_stream])
        client = Mock()
        client.chat.completions.create = create

        llm.reset_llm_call_log()
        result = llm.call_llm_until_nonempty(
            client,
            "gemini-2.5-flash",
            [{"role": "user", "content": "hello"}],
            sleep_seconds=0,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(create.call_count, 2)
        log = llm.get_llm_call_log()
        self.assertEqual(len(log), 1)
        self.assertTrue(log[0]["stream"])
        self.assertEqual(log[0]["finish_reason"], "stop")
        self.assertFalse(log[0]["cancelled_due_to_deadline"])

    def test_call_llm_until_nonempty_records_deadline_cancellation(self) -> None:
        create = Mock(return_value=[])
        client = Mock()
        client.chat.completions.create = create

        llm.reset_llm_call_log()
        with patch("src.rag_report.report_vnext.llm.time.monotonic", side_effect=[0.0, 46.0]):
            result = llm.call_llm_until_nonempty(
                client,
                "gemini-2.5-flash",
                [{"role": "user", "content": "hello"}],
                sleep_seconds=0,
                max_attempts=1,
            )

        self.assertEqual(result, "")
        log = llm.get_llm_call_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["finish_reason"], "timeout")
        self.assertTrue(log[0]["cancelled_due_to_deadline"])
        self.assertTrue(log[0]["stream"])


if __name__ == "__main__":
    unittest.main()
