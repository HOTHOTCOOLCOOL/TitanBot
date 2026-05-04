"""Exact launcher prompts for the harness_lite workflow."""


def _artifact_path(job_id: str, filename: str) -> str:
    return f".agent/artifacts/harness_lite/{job_id}/{filename}"


def build_start_launcher(job_id: str, source: str, goal: str) -> str:
    return (
        "请按 harness_lite 工作流启动任务。\n"
        f"job_id: {job_id}\n"
        f"source: {source}\n"
        f"goal: {goal}"
    )


def build_critic_launcher(job_id: str) -> str:
    return (
        "请按 harness_lite 的 Critic 阶段执行。\n"
        f"先读取 `{_artifact_path(job_id, 'problem_statement.md')}`\n"
        f"再读取 `{_artifact_path(job_id, 'baseline.md')}`\n"
        f"再读取 `{_artifact_path(job_id, 'draft_v1.md')}`\n"
        "必要时只额外读取上述 Artifact 中明确点名的 repo 文件。\n"
        "不要读取其他聊天历史，不要润色，不要替作者圆方案。\n"
        f"把结果写入 `{_artifact_path(job_id, 'review_packet.md')}`\n"
        "如任一关键 Artifact 缺失、路径不明或内容冲突，输出 BLOCKED 并停止。"
    )


def build_synthesis_launcher(job_id: str) -> str:
    return (
        f"继续 harness_lite 综合与核验，job_id={job_id}\n"
        f"请先读取 `{_artifact_path(job_id, 'review_packet.md')}`\n"
        "然后写出 `candidate.md` 并执行 Evidence Gate，结果写入 `evidence_gate.md`。\n"
        "若有关键项 FAIL 或 BLOCKED，不得宣称完成。"
    )
