from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from paperpilot.agent import AgentState, PaperPilotAgent
from paperpilot.llm import DeepSeekLLM, MockLLM, _json_from_text, create_llm
from paperpilot.tools import locate_evidence

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = (ROOT / "samples/sample_paper.txt").read_text(encoding="utf-8")

class AgentTests(unittest.TestCase):
    def run_agent(self, llm=None, text=SAMPLE, max_revisions=2):
        with TemporaryDirectory(dir=ROOT) as directory, redirect_stdout(StringIO()):
            state = PaperPilotAgent(llm, max_revisions).run(text, Path(directory))
            report = Path(state.report_path).read_text(encoding="utf-8")
        return state, report

    def test_mock_rewrites_and_rechecks(self):
        state, report = self.run_agent()
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.provider, "Mock")
        self.assertEqual(state.revision_count, 1)
        self.assertEqual([r["needs_revision"] for r in state.review_history], [True, False])
        self.assertIn("必然改善", state.draft_translation)
        self.assertIn("可能改善", state.final_translation)
        self.assertIn("Provider: Mock", report)
        self.assertIn("verified", report)

    def test_clean_review_skips_rewriter(self):
        class CleanMock(MockLLM):
            def complete(self, task, context):
                result = super().complete(task, context)
                return result.replace("必然改善", "可能改善") if task == "translate_text" else result
        state, _ = self.run_agent(CleanMock())
        self.assertEqual(state.revision_count, 0)
        self.assertNotIn("[Tool] rewrite_translation", state.execution_log)

    def test_revision_limit_keeps_failure(self):
        class StubbornMock(MockLLM):
            def complete(self, task, context):
                return context["draft_translation"] if task == "rewrite_translation" else super().complete(task, context)
        state, report = self.run_agent(StubbornMock())
        self.assertEqual(state.status, "needs_manual_review")
        self.assertEqual(state.revision_count, 2)
        self.assertEqual(len(state.review_history), 3)
        self.assertIn("达到最大修订次数", report)

    def test_fabricated_evidence_is_unverified_not_trusted(self):
        class FabricatingMock(MockLLM):
            def complete(self, task, context):
                return [{"claim_id": "C1", "quote": "A fabricated result.", "supports": "x", "limits": "y", "status": "candidate"}]
        state = AgentState(SAMPLE, claims=[{"id": "C1"}])
        result = locate_evidence(state, FabricatingMock())
        self.assertEqual(result[0]["verification_status"], "unverified")
        self.assertIsNone(result[0]["start"])

    def test_explicit_insufficient_evidence(self):
        class NoEvidence(MockLLM):
            def complete(self, task, context):
                return [{"claim_id": "C1", "quote": "", "supports": "不足", "limits": "原文未提供", "status": "insufficient_evidence"}]
        state = AgentState(SAMPLE, claims=[{"id": "C1"}])
        self.assertEqual(locate_evidence(state, NoEvidence())[0]["verification_status"], "insufficient_evidence")

    def test_tool_failure_saved(self):
        class BrokenMock(MockLLM):
            def complete(self, task, context):
                raise RuntimeError("模拟模型连接失败")
        state, report = self.run_agent(BrokenMock())
        self.assertEqual(state.status, "failed")
        self.assertIn("模拟模型连接失败", report)

    def test_json_fence_and_surrounding_text(self):
        self.assertEqual(_json_from_text('```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(_json_from_text('结果如下： {"ok": true} 完成'), {"ok": True})
        with self.assertRaises(ValueError):
            _json_from_text("not json")

    def test_provider_selection_and_missing_key(self):
        self.assertIsInstance(create_llm("mock"), MockLLM)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                create_llm("deepseek")
        with self.assertRaisesRegex(ValueError, "mock 或 deepseek"):
            create_llm("other")

    def test_deepseek_compatible_request_without_network(self):
        class Message: content = '```json\n{"topic":"主题","research_question":"问题","structure":["结果"]}\n```'
        class Choice: message = Message()
        class Response: choices = [Choice()]
        class Completions:
            def __init__(self): self.kwargs = None
            def create(self, **kwargs): self.kwargs = kwargs; return Response()
        class Chat:
            def __init__(self): self.completions = Completions()
        class Client:
            def __init__(self): self.chat = Chat()
        client = Client()
        result = DeepSeekLLM(client=client).complete("analyze_paper", {"original_text": "x"})
        self.assertEqual(result["topic"], "主题")
        self.assertEqual(client.chat.completions.kwargs["model"], "deepseek-flash")
        self.assertEqual(client.chat.completions.kwargs["response_format"], {"type": "json_object"})

    def test_empty_input_rejected(self):
        with self.assertRaises(ValueError):
            PaperPilotAgent().run(" ", ROOT / "outputs")

if __name__ == "__main__":
    unittest.main()
