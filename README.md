# PaperPilot

PaperPilot 是面向科研新人的证据驱动论文阅读与翻译 Agent。

- **v0.1 / Mock**：内置确定性教学示例，用于离线验证 Agent workflow，不代表真实论文理解质量。
- **v0.2 / DeepSeek**：通过 OpenAI Python SDK 的兼容接口调用真实 DeepSeek 模型，完成基于输入文本的分析、Claim/Evidence 提取、翻译、独立审校、修订和新人阅读指导。

## PaperPilot 的 1+1

1. **Agentic Translation**：Translate → Reflect/Review → Improve
2. **Evidence-first Paper Reading**：Claim → Evidence → Evidence Verification

论文理解结果指导翻译；Reviewer 检查译文是否忠实于论文的 Claim、Evidence、数字和限定表达；最终生成面向科研新人的证据驱动阅读报告。Python 会在本地验证模型给出的 Claim/Evidence 引文是否确实存在于输入原文中。

## 运行

环境要求：Python 3.13。DeepSeek 模式还需要 `openai` Python SDK。

Mock 模式（默认，无需网络和 API Key）：

```powershell
$env:LLM_PROVIDER="mock"
python main.py
```

DeepSeek 模式：

```powershell
$env:LLM_PROVIDER="deepseek"
$env:DEEPSEEK_API_KEY="你的 API Key"
python main.py --input samples/sample_paper.txt
```

API Key 只从进程环境变量 `DEEPSEEK_API_KEY` 读取，不得写入代码、README、测试、日志或报告。DeepSeek 配置固定为：

- `base_url`: `https://api.deepseek.com`
- `model`: `deepseek-flash`

可选参数：

```powershell
python main.py --input samples/sample_paper.txt --max-revisions 2
```

输入必须是工作区内的 UTF-8 文本文件。报告以 UTF-8 保存到 `outputs/`。

## Agent workflow

```text
Agent State → Tool Call → Observation → Decision → Next Action

Analyzer → Claim Extractor → Evidence Locator → Glossary Builder
  → Translator → Reviewer
      ├─ needs_revision=True 且未达上限 → Rewriter → Reviewer
      └─ passed / 达到上限 → Beginner Reading Coach
  → Report Writer
```

默认最多修订 2 次。达到上限仍有问题时状态为 `needs_manual_review`，报告保留 Reviewer 的未解决问题，不会伪装为通过。

每项能力都是一次独立工具/模型调用，并非用单个 Prompt 生成整份报告：

- `analyze_paper`
- `extract_claims`
- `locate_evidence`
- `build_glossary`
- `translate_text`
- `review_translation`
- `rewrite_translation`（仅 Reviewer 要求时）
- `generate_beginner_guide`
- `save_report`

## Evidence 防幻觉

模型负责寻找候选 Evidence，Python 负责逐字本地验证：

- 引文是原文连续子串：`verified`，记录行号和字符区间 `[start, end)`。
- 模型给出但原文找不到：`unverified`，不会作为已验证证据。
- 模型明确表示原文没有足够证据：`insufficient_evidence`。

Claim 引文本身也必须能在原文逐字定位，否则该工具调用失败并把清楚的错误写入执行状态和报告。字符串验证只能证明“引文来自原文”，语义支持关系仍应由用户结合完整论文核查。

## 结构化输出与失败处理

Claims、Evidence、Glossary、Review 等优先请求 JSON。解析器支持纯 JSON、Markdown `json` 代码围栏和 JSON 前后的少量说明文字，并检查关键字段。空响应、格式异常、缺字段、SDK/API/网络失败会产生明确错误；Agent 随后尽可能保存已有状态和 execution log。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试不需要真实 API Key，也不会发网络请求。它覆盖 Mock 循环、修订上限、Evidence 验证、JSON 解析、Provider 选择、缺失 Key 和 DeepSeek 兼容请求参数。

## 项目结构

```text
paperpilot/
  agent.py     # Agent State、Decision 和审校循环
  tools.py     # 工具、schema 检查、Evidence 本地验证、报告
  llm.py       # Mock 与 DeepSeek providers、提示词和 JSON 解析
samples/
tests/
outputs/
main.py
```

v0.2 仍聚焦文本 Demo，暂不包含 LangChain、Web UI、PDF、数据库、用户系统或 Docker。
