# PaperPilot

PaperPilot 是一个面向科研新手、研究生和需要阅读英文论文用户的 AI 论文阅读与学术翻译 Agent。

它不仅翻译论文，还帮助用户理解作者提出了什么 Claim、Evidence 在哪里、证据实际支持到什么程度，以及译文是否忠实保留了原文的主张、数字与限定表达。

## Why PaperPilot

科研新人在阅读英文论文时，常常面临这些问题：

- 英文论文阅读成本较高，专业术语和复杂句式会影响理解效率。
- 普通逐句翻译容易脱离论文主题、研究设计和论证语境。
- 阅读时容易只关注结论，而忽略结论背后的 Evidence。
- `may`、`suggest`、`likely` 等限定表达容易被误解或在翻译中被强化。
- 新手不容易区分“作者提出的主张”和“证据真正支持的范围”。

PaperPilot 将论文分析、证据定位、学术翻译、独立审校和新人阅读指导组织成一个可追踪的多步骤工作流。

## Features

- **Paper Analysis**：分析论文主题、研究问题和文本结构。
- **Claim Extraction**：提取作者在原文中实际提出的核心主张。
- **Evidence Location**：为 Claim 定位对应的英文 Evidence。
- **Evidence Verification**：在本地检查 Evidence 引文是否真实存在于输入文本中。
- **Academic Glossary**：提取重要学术术语，提供推荐译法和入门解释。
- **Academic Translation**：结合论文主题、Claim、Evidence 和术语表生成学术中文译文。
- **Independent Translation Review**：独立检查漏译、语义偏差、主张强度、限定表达、术语和数字。
- **Automatic Rewrite**：Reviewer 发现问题时自动修订，并再次审校。
- **Beginner Reading Guide**：生成面向科研新手的证据驱动阅读卡片。
- **Markdown Report**：将分析、翻译、审校记录和执行过程保存为 Markdown 报告。

项目同时保留离线 Mock 模式，便于在没有 API Key 时验证完整 Agent workflow。Mock 输出仅用于流程演示，不代表真实论文理解或翻译质量。

## How It Works

```text
Paper Text
    ↓
Paper Analysis
    ↓
Claim Extraction
    ↓
Evidence Location & Verification
    ↓
Glossary
    ↓
Translation
    ↓
Independent Reviewer
    ↓
Needs Revision?
    ├─ Yes → Rewriter → Reviewer
    └─ No
         ↓
Beginner Reading Guide
    ↓
Markdown Report
```

PaperPilot 使用多步骤 Agent workflow，而不是通过一次 Prompt 直接生成整份报告。每一步都会读取当前 Agent State，调用对应工具，记录 Observation，并根据结果决定 Next Action。

默认最多自动修订两次。如果达到上限后 Reviewer 仍发现问题，报告会标记为需要人工检查，不会将其伪装为审校通过。

## Quick Start

### 1. Clone

将下面的占位地址替换为本项目实际的 GitHub 仓库地址：

```bash
git clone <CURRENT_GITHUB_REPOSITORY_URL>
cd PaperPilot
```

### 2. Install

项目使用 Python 3.13，并通过 OpenAI Python SDK 的兼容接口访问 DeepSeek。当前项目没有 `requirements.txt`，请直接安装运行所需依赖：

```bash
python -m pip install openai
```

### 3. Configure DeepSeek

你需要自行准备 DeepSeek API Key。请在运行 PaperPilot 的同一个 PowerShell 窗口中设置：

```powershell
$env:DEEPSEEK_API_KEY="YOUR_API_KEY"
$env:LLM_PROVIDER="deepseek"
```

API Key 只应通过环境变量提供。不要将真实 Key 写入代码、README、测试、输出报告或提交到 Git。

如需在没有 API Key 的情况下体验离线流程，可使用 Mock 模式：

```powershell
$env:LLM_PROVIDER="mock"
```

### 4. Prepare Paper Text

当前版本接受工作区内的英文 `.txt` 文件。例如：

```text
samples/my_paper.txt
```

第一次使用时，建议从论文 Abstract 或一段较短的正文开始，以便核对 Claim、Evidence 和译文。

### 5. Run

```powershell
python main.py --input samples/my_paper.txt
```

默认最多自动修订两次，也可以显式指定：

```powershell
python main.py --input samples/my_paper.txt --max-revisions 2
```

### 6. View Result

生成的 Markdown 报告保存在：

```text
outputs/
```

报告包含：

- Paper Analysis
- Claims
- Evidence
- Evidence Verification
- Glossary
- Initial Translation
- Review History
- Final Translation
- Beginner Reading Guide
- Execution Log

## Example

项目自带公开教学示例 `samples/sample_paper.txt`，可以用于验证安装和工作流。

使用 DeepSeek：

```powershell
$env:LLM_PROVIDER="deepseek"
python main.py --input samples/sample_paper.txt
```

使用离线 Mock：

```powershell
$env:LLM_PROVIDER="mock"
python main.py --input samples/sample_paper.txt
```

## Agent Design

PaperPilot 由两个互相协作的核心能力组成。

### Evidence-aware Paper Reading

```text
Claim → Evidence → Verification
```

模型首先寻找候选 Claim 和 Evidence，随后由 Python 程序检查引用是否确实存在于用户输入的原文中：

- `verified`：引用是输入文本中的连续原文。
- `unverified`：模型给出的引用无法在输入文本中找到，不作为已验证证据。
- `insufficient_evidence`：输入文本没有提供足够 Evidence。

### Iterative Academic Translation

```text
Translate → Review → Rewrite → Review
```

Paper Reading 的结果会作为翻译和审校的上下文。Reviewer 不只检查中文是否通顺，还会检查译文是否改变了论文的 Claim、Evidence、数字以及 `may`、`suggest`、`likely` 等限定表达。

只有 Reviewer 返回 `needs_revision=True` 时，Agent 才会调用 Rewriter。修订完成后，译文会再次交给 Reviewer 检查。

## Safety / Privacy

- API Key 仅从环境变量 `DEEPSEEK_API_KEY` 读取。
- `.env` 和 `.env.*` 已加入 `.gitignore`。
- `outputs/*.md` 默认不提交到 Git。
- 用户自己的论文文本可能包含未公开内容，应避免提交到公共仓库。
- 运行前请自行确认所处理论文和数据符合相应的版权、保密及使用要求。

## Current Limitations

- 当前主要接受英文纯文本 `.txt` 文件。
- 暂不支持 PDF 解析。
- 暂无 Web UI。
- LLM 输出仍可能出现理解、翻译或结构化格式错误，重要内容需要人工核查。
- Evidence 本地验证只能确认引用是否存在于输入文本中，不代表证据一定支持对应 Claim，也不等于验证论文结论本身正确。
- 当前不解析图表、公式、补充材料或外部参考文献。

## Roadmap

- PDF parsing
- Web UI
- 更准确的页码、段落和引用位置
- Multi-section / full-paper reading
- 更完善的翻译与 Evidence 评测

以上内容是未来计划，当前版本尚未实现。

## License / Contributing

当前仓库尚未声明开源许可证。在许可证明确之前，请不要假设代码可以按某个特定许可证使用或再分发。

欢迎通过 Issue 报告问题、提出功能建议，也欢迎提交 Pull Request 改进项目。
