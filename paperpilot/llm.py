"""LLM providers for PaperPilot v0.2."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"
SAMPLE_SENTENCES = [
    "We investigate whether retrieval practice helps first-year graduate students learn scientific terminology.",
    "In a pilot study, 24 students were randomly assigned to retrieval practice or rereading for one week.",
    "The retrieval practice group scored 78% on a terminology test, compared with 65% in the rereading group.",
    "These results suggest that retrieval practice may improve short-term terminology recall.",
    "The small sample and short follow-up limit generalization; long-term retention was not measured.",
]
TRANSLATIONS = [
    "我们研究检索练习是否有助于研一学生学习科学术语。",
    "在一项先导研究中，24 名学生被随机分配到检索练习组或重读组，持续一周。",
    "检索练习组在术语测试中的得分为 78%，重读组为 65%。",
    "这些结果提示，检索练习可能改善短期术语回忆。",
    "样本量小且随访时间短限制了结果的可推广性；研究未测量长期保持效果。",
]

class LLM(Protocol):
    provider_name: str
    def complete(self, task: str, context: dict[str, Any]) -> Any: ...

def _json_from_text(content: str) -> Any:
    """Parse JSON returned directly or inside a Markdown code fence."""
    if not content or not content.strip():
        raise ValueError("模型返回了空内容")
    stripped = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.I | re.S)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        decoder = json.JSONDecoder()
        for start, char in enumerate(stripped):
            if char in "[{":
                try:
                    value, _ = decoder.raw_decode(stripped[start:])
                    return value
                except json.JSONDecodeError:
                    pass
        raise ValueError(f"模型返回的 JSON 无法解析：{exc.msg}") from exc

SYSTEM_PROMPT = """你是 PaperPilot 的科研论文阅读组件。只依据用户给出的英文原文和工作流状态回答，不得补写原文不存在的事实、主张或证据。quote 必须逐字复制原文中的连续文本。严格遵循任务要求的输出格式。"""
TASK_PROMPTS = {
    "analyze_paper": "分析主题、研究问题和文本结构。返回 JSON 对象：topic、research_question、structure（字符串数组）。",
    "extract_claims": "提取作者真正提出的核心主张。返回 JSON 对象 {\"claims\": [...]}，数组每项含 id（C1 起）、quote（逐字原文）、meaning。没有则为空数组。",
    "locate_evidence": "为每个 Claim 寻找证据。返回 JSON 对象 {\"evidence\": [...]}，数组每项含 claim_id、quote（逐字原文）、supports、limits、status（candidate 或 insufficient_evidence）。没有足够证据时 quote 为空且 status 为 insufficient_evidence，严禁编造。",
    "build_glossary": "提取科研新人可能不熟悉的术语。返回 JSON 对象 {\"glossary\": [...]}，数组每项含 english、chinese、explanation。",
    "translate_text": "根据分析、Claims、Evidence 和术语表，将英文完整忠实地译为学术中文。保留 may/suggest/likely 的强度、数字和局限。只返回译文。",
    "review_translation": "独立审校当前译文的漏译、语义、Claim 强度、限定表达、术语、数字和学术中文。返回 JSON：status（passed/issues_found）、needs_revision（布尔）、issues（数组）、revision_advice（数组）、checks（对象，含 omission、semantics、claim_strength、qualifiers、terminology、numbers、academic_chinese 布尔项）。",
    "rewrite_translation": "依据原文、当前译文、审校问题、术语表、Claims 和 Evidence 修订。只返回完整译文。",
    "generate_beginner_guide": "返回 JSON 对象，含九个中文键：这段主要在讲什么、作者想解决什么问题、作者的核心 Claim、Evidence 在哪里、Evidence 实际支持什么、Evidence 不能证明什么、必须理解的术语、第一次阅读重点、读后自测。值为中文字符串。",
}
JSON_TASKS = {"analyze_paper", "extract_claims", "locate_evidence", "build_glossary", "review_translation", "generate_beginner_guide"}

class DeepSeekLLM:
    """DeepSeek client using the OpenAI-compatible SDK."""
    provider_name = "DeepSeek"

    def __init__(self, api_key: str | None = None, client: Any | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if client is None and not key:
            raise ValueError("DeepSeek 模式需要环境变量 DEEPSEEK_API_KEY；请在运行 PaperPilot 的同一终端中设置它。")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("DeepSeek 模式需要 openai Python SDK，请先安装 openai。") from exc
            client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        self.client = client

    def complete(self, task: str, context: dict[str, Any]) -> Any:
        if task not in TASK_PROMPTS:
            raise ValueError(f"未知模型任务：{task}")
        kwargs: dict[str, Any] = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"任务：{TASK_PROMPTS[task]}\n\n工作流状态：\n{json.dumps(context, ensure_ascii=False, default=str)}"},
            ],
            "temperature": 0,
        }
        if task in JSON_TASKS:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
        except Exception as exc:
            raise RuntimeError(f"DeepSeek API 请求失败：{type(exc).__name__}: {exc}") from exc
        if not content or not content.strip():
            raise ValueError("DeepSeek 返回了空内容")
        if task not in JSON_TASKS:
            return content.strip()
        parsed = _json_from_text(content)
        collection_keys = {"extract_claims": "claims", "locate_evidence": "evidence", "build_glossary": "glossary"}
        key = collection_keys.get(task)
        if key:
            if not isinstance(parsed, dict) or key not in parsed:
                raise ValueError(f"模型 JSON 缺少顶层字段 {key}")
            return parsed[key]
        return parsed

class MockLLM:
    """Deterministic v0.1 provider retained for offline workflow tests."""
    provider_name = "Mock"

    def complete(self, task: str, context: dict[str, Any]) -> Any:
        text = context["original_text"]
        known = " ".join(text.split()) == " ".join(SAMPLE_SENTENCES)
        if task == "analyze_paper":
            return {"topic": "检索练习与科研术语学习" if known else "未知主题（超出 Mock 示例范围）", "research_question": "检索练习能否帮助研一学生学习科学术语？" if known else "Mock 无法分析", "structure": ["研究问题", "实验设计", "结果", "主张", "局限"] if known else ["用户输入片段"], "mock_supported": known}
        if task == "extract_claims":
            return [{"id": "C1", "quote": SAMPLE_SENTENCES[3], "meaning": "检索练习可能改善短期术语回忆，属于有限定的主张。"}] if known else []
        if task == "locate_evidence":
            return [{"claim_id": "C1", "quote": SAMPLE_SENTENCES[2], "supports": "该先导研究中检索练习组得分高于重读组，相差 13 个百分点。", "limits": "未给出显著性检验或置信区间；不能认定普遍或长期有效。", "status": "candidate"}] if known else []
        if task == "build_glossary":
            return [{"english": "retrieval practice", "chinese": "检索练习", "explanation": "通过主动回忆已学内容进行练习。"}, {"english": "pilot study", "chinese": "先导研究", "explanation": "进一步研究前的小规模探索。"}, {"english": "generalization", "chinese": "可推广性", "explanation": "结果能否适用于其他人群或情境。"}, {"english": "long-term retention", "chinese": "长期保持", "explanation": "较长时间后仍能记住内容的程度。"}] if known else []
        if task == "translate_text":
            return "\n".join(TRANSLATIONS).replace("可能改善", "必然改善") if known else "【Mock 未翻译】请使用 DeepSeek 模式。\n\n" + text
        if task == "review_translation":
            if not known:
                return {"needs_revision": False, "status": "unsupported", "issues": ["Mock 无法评估自定义文本。"], "revision_advice": [], "checks": {}}
            translation = context["final_translation"] or context["draft_translation"]
            checks = {"omission": all(s in translation for s in [TRANSLATIONS[0], TRANSLATIONS[1], TRANSLATIONS[2], TRANSLATIONS[4]]), "semantics": TRANSLATIONS[3] in translation, "claim_strength": "必然改善" not in translation, "qualifiers": "可能改善" in translation, "terminology": "检索练习" in translation, "numbers": "78%" in translation and "65%" in translation, "academic_chinese": all(s in translation for s in TRANSLATIONS)}
            issues = [f"{name}：需要修订（示例规则检查）" for name, passed in checks.items() if not passed]
            return {"needs_revision": bool(issues), "status": "issues_found" if issues else "passed", "issues": issues, "revision_advice": ["忠实保留限定强度。"] if issues else [], "checks": checks}
        if task == "rewrite_translation":
            return "\n".join(TRANSLATIONS) if known else (_ for _ in ()).throw(ValueError("Mock 不支持修订此文本"))
        if task == "generate_beginner_guide":
            if not known:
                return {"当前状态": "超出 Mock 范围，没有生成实质性分析。"}
            return {"这段主要在讲什么": "一项比较检索练习与重读的短期先导研究。", "作者想解决什么问题": "检索练习能否帮助研一学生学习科学术语？", "作者的核心 Claim": "C1：检索练习可能改善短期术语回忆。", "Evidence 在哪里": "E1：原文第三句，78% 与 65% 的得分比较。", "Evidence 实际支持什么": "仅支持本次样本中的得分差异。", "Evidence 不能证明什么": "不能证明长期效果、普遍有效或统计显著性。", "必须理解的术语": "检索练习、先导研究、可推广性、长期保持。", "第一次阅读重点": "区分研究设计、数值结果、作者解释和局限。", "读后自测": "研究有多少人、持续多久？两组差多少？为什么不能说长期有效？"}
        raise ValueError(f"未知模型任务：{task}")

def create_llm(provider: str | None = None) -> LLM:
    selected = (provider or os.getenv("LLM_PROVIDER", "mock")).strip().lower()
    if selected == "mock":
        return MockLLM()
    if selected == "deepseek":
        return DeepSeekLLM()
    raise ValueError("LLM_PROVIDER 必须是 mock 或 deepseek")
