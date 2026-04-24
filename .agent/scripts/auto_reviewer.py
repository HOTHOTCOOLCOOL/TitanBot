#!/usr/bin/env python3
"""
auto_reviewer.py

Automated L2 Codex Review Script.
Extracts git diff for specified files and sends a rigorous review request to gpt-5.4.
"""
import sys
import argparse
import asyncio
import subprocess
from pathlib import Path

# Ensure nanobot package is in module path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nanobot.providers.litellm_provider import LiteLLMProvider

PROMPT_TEMPLATE = """【系统背景：Nanobot 框架正在实施 Phase 自动化 L2 Review，重点检查点为：{context}】

以下是你需要审查的代码变更 (Git Diff)：
```diff
{diff_content}
```

请严格遵循以下 6 条审查铁律进行回复：
1. 先做契约检查：不要先看代码怎么修的，必须先审视“规格/业务契约要求的行为是否已准确恢复”（例如：核心路径对合法输入是否生效，底层致命异常是否被静默吞噬）。
2. 先输出问题分类表，不允许按 API 名字碎片化报告。任何修复绕过或同类新入口，必须归入大类并标记“同类回归”。
3. 针对每类问题，必须一次性列出所有已知残留面，绝不允许分多轮挤牙膏。
4. 【定级双红线】审查结果必须严格按以下证据分级：
   - A 级（核心硬伤）：具备安全最小复现利用链，或者核心业务流被确定性打断、发生静默失效、业务无输出但看似成功等破坏核心契约的致命缺陷（必须修）。
   - B 级（明确风险）：具备能力面隐患但无完整 PoC，或架构实现存在可预见的高耦合/性能瓶颈（必须评估）。
   - C 级（理论担忧）：不影响生产基线的纯理论隐患（只入风险清单）。
5. 【真实路径一致性审查】不仅要检视高风险代码是否配套了 Adversarial Tests，更必须严厉审视这些测试是否真正模拟了生产中会发生的失效机制。如果发现测试依赖人工造假条件、规避了真实主流程或只覆盖替代路径，必须将该防御记为不充分。
6. 如果发现某类问题已连续两轮触发“同类回归”，请直接判定根因未闭环，并指出其“只是压住了表面症状而没有恢复系统级契约”，下达禁止继续堆叠底层胶水补丁、强制彻底重构的指令。

结论只允许二选一：
1. 审查通过，架构漏洞已全链路闭环，开始收尾
2. 未通过，并附证据分级后的分类分类残留表
"""

async def run_review(files: list[str], context: str):
    cmd = ["git", "diff", "HEAD", "--"] + files
    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    diff_content = result.stdout.strip()
    
    if not diff_content:
        cmd_st = ["git", "diff", "--staged", "--"] + files
        result_st = subprocess.run(cmd_st, capture_output=True, text=True, encoding='utf-8')
        diff_content = result_st.stdout.strip()

        if not diff_content:
            print("[!] No diff found for the specified files (neither unstaged nor staged).")
            return

    # Truncation for token explosion prevention
    if len(diff_content) > 30000:
        print(f"[!] Warning: Diff is huge ({len(diff_content)} chars). Truncating to 30000 characters to prevent Token Explosion.")
        diff_content = diff_content[:30000] + "\n...[TRUNCATED]"

    prompt = PROMPT_TEMPLATE.format(context=context, diff_content=diff_content)
    
    print("[*] Connecting to LLM Provider (gpt-5.4)...")
    provider = LiteLLMProvider(default_model="gpt-5.4")
    
    messages = [
        {"role": "system", "content": "You are Codex, the elite L2 architectural reviewer and ruthless gatekeeper for the Nanobot project. You do not appease the developer; you are strictly critical."},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = await provider.chat(messages=messages, temperature=0.2, max_tokens=4000)
        print("\n" + "="*60)
        print("🤖 [CODEX L2 REVIEW RESULTS]")
        print("="*60)
        print(response.content)
        print("="*60 + "\n")
    except Exception as e:
        print(f"[!] Error calling LLM: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Codex L2 Reviewer")
    parser.add_argument("--files", nargs="*", default=[], help="Specific files to diff and review (leave empty for all)")
    parser.add_argument("--context", type=str, required=True, help="Short background context for the review session")
    
    args = parser.parse_args()
    
    asyncio.run(run_review(args.files, args.context))
