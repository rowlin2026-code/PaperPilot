"""PaperPilot v0.2 command-line entry point."""
import argparse
from pathlib import Path
import sys

from paperpilot.agent import PaperPilotAgent
from paperpilot.llm import create_llm

ROOT = Path(__file__).resolve().parent

def workspace_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("只能访问当前工作区内的路径")
    return path

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="PaperPilot v0.2 — Mock / DeepSeek Agent workflow")
    parser.add_argument("--input", default="samples/sample_paper.txt", help="工作区内 UTF-8 文本文件")
    parser.add_argument("--max-revisions", type=int, default=2, help="最大修订次数，默认 2")
    args = parser.parse_args()
    try:
        text = workspace_path(args.input).read_text(encoding="utf-8-sig")
        llm = create_llm()
        state = PaperPilotAgent(llm=llm, max_revisions=args.max_revisions).run(text, workspace_path("outputs"))
        print(f"[Agent] 结束：provider={state.provider}，状态={state.status}，修订={state.revision_count} 次")
        return 0 if state.status == "completed" else 1
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
