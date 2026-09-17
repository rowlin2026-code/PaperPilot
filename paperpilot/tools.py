"""PaperPilot tools, schema checks, local evidence verification and reporting."""
from datetime import datetime
from pathlib import Path
from typing import Any

from .llm import LLM

def _call(llm: LLM, task: str, state: Any) -> Any:
    return llm.complete(task, state.context())

def _require(value: Any, expected: type, name: str) -> Any:
    if not isinstance(value, expected):
        raise ValueError(f"模型结果字段 {name} 缺失或类型错误")
    return value

def _anchor(text: str, quote: str) -> dict[str, Any] | None:
    if not isinstance(quote, str) or not quote.strip():
        return None
    start = text.find(quote)
    if start < 0:
        return None
    return {"start": start, "end": start + len(quote), "line": text.count("\n", 0, start) + 1}

def analyze_paper(state, llm):
    result = _require(_call(llm, "analyze_paper", state), dict, "analysis")
    _require(result.get("topic"), str, "topic")
    _require(result.get("structure"), list, "structure")
    return result

def extract_claims(state, llm):
    claims = _require(_call(llm, "extract_claims", state), list, "claims")
    ids: set[str] = set()
    verified = []
    for claim in claims:
        _require(claim, dict, "claim")
        claim_id = _require(claim.get("id"), str, "claim.id")
        quote = _require(claim.get("quote"), str, "claim.quote")
        _require(claim.get("meaning"), str, "claim.meaning")
        if claim_id in ids:
            raise ValueError("Claim ID 重复")
        anchor = _anchor(state.original_text, quote)
        if anchor is None:
            raise ValueError(f"{claim_id} 的原文引用无法在输入文本中验证")
        ids.add(claim_id)
        verified.append({**claim, **anchor, "verification_status": "verified"})
    return verified

def locate_evidence(state, llm):
    candidates = _require(_call(llm, "locate_evidence", state), list, "evidence")
    claim_ids = {c["id"] for c in state.claims}
    evidence = []
    for index, raw in enumerate(candidates, 1):
        _require(raw, dict, "evidence item")
        claim_id = _require(raw.get("claim_id"), str, "evidence.claim_id")
        if claim_id not in claim_ids:
            raise ValueError("Evidence 指向不存在的 Claim")
        item = {
            "id": f"E{index}", "claim_id": claim_id,
            "quote": raw.get("quote", "") if isinstance(raw.get("quote", ""), str) else "",
            "supports": raw.get("supports", "未说明"), "limits": raw.get("limits", "未说明"),
        }
        anchor = _anchor(state.original_text, item["quote"])
        requested_insufficient = raw.get("status") == "insufficient_evidence"
        if requested_insufficient or anchor is None:
            item.update({"verification_status": "insufficient_evidence" if requested_insufficient else "unverified", "start": None, "end": None, "line": None})
            if anchor is None and item["quote"]:
                item["limits"] = f"本地验证未在原文找到该引用；不得作为已验证证据。{item['limits']}"
        else:
            item.update(anchor)
            item["verification_status"] = "verified"
        evidence.append(item)
    return evidence

def build_glossary(state, llm):
    result = _require(_call(llm, "build_glossary", state), list, "glossary")
    for term in result:
        _require(term, dict, "glossary item")
        for field in ("english", "chinese", "explanation"):
            _require(term.get(field), str, f"glossary.{field}")
    return result

def translate_text(state, llm):
    return _require(_call(llm, "translate_text", state), str, "translation")

def review_translation(state, llm):
    result = _require(_call(llm, "review_translation", state), dict, "review")
    if type(result.get("needs_revision")) is not bool:
        raise ValueError("审校结果必须包含布尔型 needs_revision")
    if result.get("status") not in {"passed", "issues_found", "unsupported"}:
        raise ValueError("审校状态无效")
    for field, kind in (("issues", list), ("revision_advice", list), ("checks", dict)):
        _require(result.get(field), kind, f"review.{field}")
    return result

def rewrite_translation(state, llm):
    if not state.review_result.get("needs_revision"):
        raise ValueError("Reviewer 未要求修订，不能调用 Rewriter")
    return _require(_call(llm, "rewrite_translation", state), str, "rewritten translation")

def generate_beginner_guide(state, llm):
    return _require(_call(llm, "generate_beginner_guide", state), dict, "beginner guide")

def save_report(state, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"paperpilot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.md"
    provider = state.provider
    lines = ["# PaperPilot 阅读报告", "", f"> PaperPilot v0.2 | Provider: {provider}", "", f"- 运行状态：{state.status}", f"- 修订次数：{state.revision_count}", f"- 审校状态：{state.review_result.get('status', '未完成')}", "", "## 原始论文文本", "", state.original_text, "", "## 论文分析", "", f"- 主题：{state.analysis.get('topic', '未完成')}", f"- 研究问题：{state.analysis.get('research_question', '未说明')}", f"- 文本结构：{' / '.join(state.analysis.get('structure', []))}", "", "## Claims", ""]
    for claim in state.claims:
        lines += [f"### {claim['id']}", "", claim["meaning"], "", f"> {claim['quote']}", "", f"位置：第 {claim['line']} 行，字符 [{claim['start']}, {claim['end']})；验证状态：{claim['verification_status']}", ""]
    if not state.claims:
        lines.append("未提取到 Claim。")
    lines += ["", "## Evidence", ""]
    for item in state.evidence:
        lines += [f"### {item['id']} → {item['claim_id']}", "", f"验证状态：**{item['verification_status']}**", "", f"> {item['quote'] or 'insufficient evidence'}", ""]
        if item["line"] is not None:
            lines.append(f"位置：第 {item['line']} 行，字符 [{item['start']}, {item['end']})。")
        lines += [f"支持范围：{item['supports']}", f"证据局限：{item['limits']}", ""]
    if not state.evidence:
        lines.append("输入文本中未定位到候选 Evidence。")
    lines += ["", "## 术语表", ""]
    lines += [f"- {t['english']} / **{t['chinese']}**：{t['explanation']}" for t in state.glossary]
    lines += ["", "## 初译", "", state.draft_translation or "未完成", "", "## Reviewer 审校记录", ""]
    for i, review in enumerate(state.review_history, 1):
        lines += [f"### 第 {i} 次审校：{review['status']}"]
        lines += [f"- {name}：{'通过' if passed else '需修订'}" for name, passed in review["checks"].items()]
        lines += [f"- 问题：{issue}" for issue in review["issues"]]
        lines += [f"- 建议：{advice}" for advice in review["revision_advice"]]
    lines += ["", "## 最终译文", "", state.final_translation or "未完成", "", "## 科研新人阅读卡片", ""]
    for title, value in state.beginner_guide.items():
        lines += [f"### {title}", "", str(value), ""]
    lines += ["## 错误与限制", ""] + ([f"- {e}" for e in state.errors] or ["- 无执行错误。模型输出仍需用户结合完整论文核查。"])
    lines += ["", "## Execution log", "", "```text", *state.execution_log, "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
