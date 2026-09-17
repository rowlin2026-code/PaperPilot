"""Explicit PaperPilot state machine and Reviewer/Rewriter loop."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import tools
from .llm import LLM, create_llm

@dataclass
class AgentState:
    original_text: str
    provider: str = "Unknown"
    analysis: dict = field(default_factory=dict)
    claims: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    glossary: list = field(default_factory=list)
    draft_translation: str = ""
    review_result: dict = field(default_factory=dict)
    final_translation: str = ""
    beginner_guide: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    execution_log: list[str] = field(default_factory=list)
    review_history: list = field(default_factory=list)
    revision_count: int = 0
    status: str = "running"
    next_action: str = "analyze_paper"
    report_path: str = ""

    def context(self) -> dict[str, Any]:
        return asdict(self)

STEPS = {
    "analyze_paper": ("analysis", "extract_claims", "开始分析论文"),
    "extract_claims": ("claims", "locate_evidence", "提取核心 Claim"),
    "locate_evidence": ("evidence", "build_glossary", "寻找并验证 Evidence"),
    "build_glossary": ("glossary", "translate_text", "建立术语表"),
    "translate_text": ("draft_translation", "review_translation", "Translator 开始初译"),
    "review_translation": ("review_result", None, "Reviewer 独立审校"),
    "rewrite_translation": ("final_translation", "review_translation", "Rewriter 根据审校意见修订"),
    "generate_beginner_guide": ("beginner_guide", "save_report", "生成科研新人阅读指导"),
}

class PaperPilotAgent:
    def __init__(self, llm: LLM | None = None, max_revisions: int = 2):
        if max_revisions < 0:
            raise ValueError("最大修订次数不能为负数")
        self.llm = llm if llm is not None else create_llm()
        self.max_revisions = max_revisions

    def log(self, state: AgentState, kind: str, message: str) -> None:
        line = f"[{kind}] {message}"
        state.execution_log.append(line)
        print(line, flush=True)

    def run(self, text: str, output_dir: Path) -> AgentState:
        if not text.strip():
            raise ValueError("论文文本不能为空")
        state = AgentState(original_text=text, provider=self.llm.provider_name)
        while state.next_action != "done":
            action = state.next_action
            try:
                if action == "save_report":
                    self.log(state, "Tool", action)
                    state.report_path = str(tools.save_report(state, output_dir))
                    self.log(state, "Observation", f"报告已保存：{state.report_path}")
                    state.next_action = "done"
                    continue
                field_name, next_action, message = STEPS[action]
                self.log(state, "Agent", message)
                self.log(state, "Tool", action)
                result = getattr(tools, action)(state, self.llm)
                setattr(state, field_name, result)
                summary = f"获得 {len(result)} 项/字符"
                if action == "review_translation":
                    summary = f"status={result['status']}, needs_revision={result['needs_revision']}"
                self.log(state, "Observation", summary)

                if action == "review_translation":
                    state.review_history.append(result)
                    if result["needs_revision"] and state.revision_count < self.max_revisions:
                        next_action = "rewrite_translation"
                        self.log(state, "Agent", "发现问题，进入 Rewriter")
                    else:
                        next_action = "generate_beginner_guide"
                        state.final_translation = state.final_translation or state.draft_translation
                        if result["needs_revision"]:
                            state.status = "needs_manual_review"
                            state.errors.append("达到最大修订次数，Reviewer 仍发现问题；最终译文需要人工核查。")
                        elif result["status"] == "unsupported":
                            state.status = "unsupported"
                        else:
                            state.status = "completed"
                elif action == "rewrite_translation":
                    state.revision_count += 1
                self.log(state, "Decision", f"{action} → {next_action}")
                state.next_action = next_action
            except Exception as exc:
                state.errors.append(f"{action}: {type(exc).__name__}: {exc}")
                self.log(state, "Error", state.errors[-1])
                state.status = "failed"
                state.next_action = "done" if action == "save_report" else "save_report"
        return state
