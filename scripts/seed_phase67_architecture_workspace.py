from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime
from pathlib import Path

from nanobot.agent.vector_store import VectorMemory
from nanobot.config.loader import get_config, get_config_path

SEED_NAME = "phase67_architecture_seed"
START_MARKER = "<!-- phase67_architecture_seed:start -->"
END_MARKER = "<!-- phase67_architecture_seed:end -->"
GRAPH_ONLY_STATE_FILE = "phase67_graph_only_mode_state.json"
GRAPH_ONLY_CONFIG_BACKUP = "phase67_graph_only_mode_config_backup.json"

GRAPH_TRIPLES = [
    {"source": "系统架构设计", "predicate": "涵盖", "target": "业务架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "应用架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "数据架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "集成架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "部署与基础设施架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "安全架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "稳定性与可靠性架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "可观测性与运维架构"},
    {"source": "系统架构设计", "predicate": "涵盖", "target": "开发治理与交付架构"},
    {"source": "系统架构设计", "predicate": "常用方法", "target": "架构方法论"},
    {"source": "业务架构", "predicate": "关注", "target": "业务能力地图"},
    {"source": "业务架构", "predicate": "关注", "target": "业务流程编排"},
    {"source": "业务架构", "predicate": "关注", "target": "领域事件"},
    {"source": "业务架构", "predicate": "关注", "target": "上下游边界"},
    {"source": "应用架构", "predicate": "关注", "target": "DDD"},
    {"source": "应用架构", "predicate": "关注", "target": "限界上下文"},
    {"source": "应用架构", "predicate": "关注", "target": "模块化单体"},
    {"source": "应用架构", "predicate": "关注", "target": "微服务拆分"},
    {"source": "应用架构", "predicate": "关注", "target": "六边形架构"},
    {"source": "数据架构", "predicate": "关注", "target": "领域模型"},
    {"source": "数据架构", "predicate": "关注", "target": "CQRS"},
    {"source": "数据架构", "predicate": "关注", "target": "Event Sourcing"},
    {"source": "数据架构", "predicate": "关注", "target": "缓存策略"},
    {"source": "数据架构", "predicate": "关注", "target": "分库分表"},
    {"source": "集成架构", "predicate": "关注", "target": "API Gateway"},
    {"source": "集成架构", "predicate": "关注", "target": "事件驱动架构"},
    {"source": "集成架构", "predicate": "关注", "target": "Outbox Pattern"},
    {"source": "集成架构", "predicate": "关注", "target": "Saga"},
    {"source": "集成架构", "predicate": "关注", "target": "幂等设计"},
    {"source": "部署与基础设施架构", "predicate": "关注", "target": "Kubernetes"},
    {"source": "部署与基础设施架构", "predicate": "关注", "target": "Service Mesh"},
    {"source": "部署与基础设施架构", "predicate": "关注", "target": "基础设施即代码"},
    {"source": "部署与基础设施架构", "predicate": "关注", "target": "蓝绿发布"},
    {"source": "安全架构", "predicate": "关注", "target": "Zero Trust"},
    {"source": "安全架构", "predicate": "关注", "target": "OAuth/OIDC"},
    {"source": "安全架构", "predicate": "关注", "target": "Secrets 管理"},
    {"source": "安全架构", "predicate": "关注", "target": "最小权限"},
    {"source": "稳定性与可靠性架构", "predicate": "关注", "target": "限流"},
    {"source": "稳定性与可靠性架构", "predicate": "关注", "target": "熔断"},
    {"source": "稳定性与可靠性架构", "predicate": "关注", "target": "重试退避"},
    {"source": "稳定性与可靠性架构", "predicate": "关注", "target": "降级"},
    {"source": "稳定性与可靠性架构", "predicate": "关注", "target": "容量评估"},
    {"source": "可观测性与运维架构", "predicate": "关注", "target": "日志"},
    {"source": "可观测性与运维架构", "predicate": "关注", "target": "指标"},
    {"source": "可观测性与运维架构", "predicate": "关注", "target": "分布式追踪"},
    {"source": "可观测性与运维架构", "predicate": "关注", "target": "告警噪音治理"},
    {"source": "开发治理与交付架构", "predicate": "关注", "target": "ADR"},
    {"source": "开发治理与交付架构", "predicate": "关注", "target": "架构评审"},
    {"source": "开发治理与交付架构", "predicate": "关注", "target": "平台工程"},
    {"source": "开发治理与交付架构", "predicate": "关注", "target": "CI/CD"},
    {"source": "架构方法论", "predicate": "包含", "target": "C4 模型"},
    {"source": "架构方法论", "predicate": "包含", "target": "4+1 视图"},
    {"source": "架构方法论", "predicate": "包含", "target": "TOGAF"},
    {"source": "架构方法论", "predicate": "包含", "target": "演进式架构"},
]

GRAPH_ALIASES = {
    "系统设计": "系统架构设计",
    "软件架构": "系统架构设计",
    "应用层架构": "应用架构",
    "基础设施架构": "部署与基础设施架构",
    "运维架构": "可观测性与运维架构",
    "可靠性架构": "稳定性与可靠性架构",
}

HISTORY_SEED_BODY = """[2026-05-04 07:20] 架构检索提示：关于架构主题的资料更适合按领域拆分检索，例如应用架构、数据架构、集成架构、可靠性、可观测性与交付治理，而不是只搜“系统架构设计”。先看领域地图，再细化关键词，通常命中更稳定。

[2026-05-04 07:21] 学习记录：应用架构相关内容覆盖 DDD、限界上下文、聚合根、模块化单体、微服务拆分与六边形架构。做检索时，优先使用“DDD / 限界上下文 / 模块化单体 / 微服务边界”。

[2026-05-04 07:22] 学习记录：数据架构相关内容覆盖领域模型、CQRS、Event Sourcing、缓存策略与分库分表。做检索时，优先使用“CQRS / 事件溯源 / 缓存一致性 / 分库分表”。

[2026-05-04 07:23] 学习记录：集成架构相关内容覆盖 API Gateway、事件驱动架构、Outbox、Saga 与幂等设计。做检索时，优先使用“API Gateway / 事件驱动 / Outbox / Saga / 幂等键”。

[2026-05-04 07:24] 学习记录：稳定性与可靠性架构相关内容覆盖限流、熔断、重试退避、降级、容量评估。做检索时，优先使用“限流 / 熔断 / 重试退避 / 降级 / 容量评估”。

[2026-05-04 07:25] 学习记录：可观测性与运维架构相关内容覆盖日志、指标、分布式追踪、告警噪音治理。做检索时，优先使用“日志 / Metrics / Tracing / SLO / 告警治理”。

[2026-05-04 07:26] 学习记录：开发治理与交付架构相关内容覆盖 ADR、架构评审、平台工程、CI/CD。做检索时，优先使用“ADR / 架构评审 / 平台工程 / CI/CD”。"""

DAILY_SEED_BODY = """- Phase 67 手测种子：已补充系统架构设计领域地图，重点覆盖业务架构、应用架构、数据架构、集成架构、基础设施、安全、可靠性、可观测性、交付治理与方法论。

- Phase 67 手测提示：如果用户用“系统架构设计”这类过宽关键词提问，优先通过领域地图把搜索词细化到 DDD、CQRS、Outbox、Saga、Zero Trust、SLO/SLI、ADR 等更具体主题。"""


def _read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8-sig")
    return ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path) -> dict | list:
    return json.loads(_read_text(path))


def _seed_block(body: str) -> str:
    return f"{START_MARKER}\n{body.rstrip()}\n{END_MARKER}\n"


def _remove_existing_seed_block(content: str) -> str:
    start = content.find(START_MARKER)
    if start == -1:
        return content
    end = content.find(END_MARKER, start)
    if end == -1:
        return content[:start].rstrip()
    return (content[:start] + content[end + len(END_MARKER):]).strip()


def _append_seed_block(path: Path, body: str) -> None:
    existing = _remove_existing_seed_block(_read_text(path))
    block = _seed_block(body).strip()
    if existing.strip():
        content = existing.rstrip() + "\n\n" + block + "\n"
    else:
        content = block + "\n"
    _write_text(path, content)


def _backup_path_for(path: Path, workspace: Path, backup_dir: Path) -> Path:
    rel = path.relative_to(workspace)
    return backup_dir / rel


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _create_backup(workspace: Path, paths: list[Path]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = workspace / "memory" / "_manual_seed_backups" / f"{SEED_NAME}_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, dict[str, object]] = {}
    for path in paths:
        rel = str(path.relative_to(workspace))
        entry = {
            "relative_path": rel,
            "exists": path.exists(),
            "is_dir": path.is_dir() if path.exists() else False,
        }
        manifest[rel] = entry
        if path.exists():
            _copy_path(path, _backup_path_for(path, workspace, backup_dir))

    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_dir


def _merge_graph(graph_path: Path) -> int:
    existing: dict[str, object] = {"triples": [], "_aliases": {}}
    if graph_path.exists():
        try:
            existing = _read_json(graph_path)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Cannot seed graph.json because it is not valid JSON: {exc}") from exc

    triples = existing.get("triples", [])
    aliases = existing.get("_aliases", {})
    if not isinstance(triples, list):
        triples = []
    if not isinstance(aliases, dict):
        aliases = {}

    seen = set()
    merged: list[dict[str, str]] = []

    for triple in triples + GRAPH_TRIPLES:
        source = str(triple.get("source", "")).strip()
        predicate = str(triple.get("predicate", "")).strip()
        target = str(triple.get("target", "")).strip()
        if not source or not predicate or not target:
            continue
        key = (source, predicate, target)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "source": source,
                "predicate": predicate,
                "target": target,
                "context": str(triple.get("context") or "Phase 67 architecture manual test seed"),
            }
        )

    aliases.update(GRAPH_ALIASES)
    payload = {"triples": merged, "_aliases": aliases}
    _write_text(graph_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return len(merged)


def _configured_embedding_model() -> str | None:
    try:
        config = get_config()
        return config.agents.defaults.embedding_model or None
    except Exception:
        return None


def apply_seed(workspace: Path, mode: str = "full") -> int:
    memory_dir = workspace / "memory"
    graph_path = memory_dir / "graph.json"
    history_path = memory_dir / "HISTORY.md"
    daily_path = memory_dir / f"{date.today().isoformat()}.md"
    vectordb_path = memory_dir / "vectordb"

    backup_dir = _create_backup(workspace, [graph_path, history_path, daily_path, vectordb_path])
    merged_triples = _merge_graph(graph_path)
    history_chunks = 0
    daily_chunks = 0

    if mode == "full":
        _append_seed_block(history_path, HISTORY_SEED_BODY)
        _append_seed_block(daily_path, DAILY_SEED_BODY)

        vm = VectorMemory(workspace, embedding_model=_configured_embedding_model())
        history_chunks = vm.ingest_text(
            HISTORY_SEED_BODY,
            source="history",
            metadata={"file_path": str(history_path)},
        )
        daily_chunks = vm.ingest_text(
            DAILY_SEED_BODY,
            source=f"daily_log:{date.today().isoformat()}",
            metadata={
                "date": date.today().isoformat(),
                "file_path": str(daily_path),
            },
        )

    print(f"Seed applied to workspace: {workspace}")
    print(f"Seed mode: {mode}")
    print(f"Backup directory: {backup_dir}")
    print(f"graph.json triples: {merged_triples}")
    print(f"history chunks ingested: {history_chunks}")
    print(f"daily log chunks ingested: {daily_chunks}")
    return 0


def restore_seed(workspace: Path, backup_dir: Path) -> int:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Backup manifest not found: {manifest_path}")

    manifest = _read_json(manifest_path)
    for rel, entry in manifest.items():
        target = workspace / rel
        backup_path = backup_dir / rel
        existed = bool(entry.get("exists"))
        is_dir = bool(entry.get("is_dir"))

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        if existed:
            _copy_path(backup_path, target)
        elif is_dir:
            target.mkdir(parents=True, exist_ok=True)

    print(f"Seed restored from backup: {backup_dir}")
    print("Note: restart the Nanobot service after restore for a clean runtime state.")
    return 0


def _latest_seed_backup_dir(workspace: Path) -> Path:
    backup_root = workspace / "memory" / "_manual_seed_backups"
    candidates = sorted(
        [p for p in backup_root.glob(f"{SEED_NAME}_*") if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No backup directories found under {backup_root}")
    return candidates[0]


def _state_root(workspace: Path) -> Path:
    root = workspace / "memory" / "_manual_seed_backups"
    root.mkdir(parents=True, exist_ok=True)
    return root


def enter_graph_only_mode(workspace: Path, restore_from_backup: Path | None = None) -> int:
    restore_backup_dir = restore_from_backup or _latest_seed_backup_dir(workspace)
    state_root = _state_root(workspace)
    state_file = state_root / GRAPH_ONLY_STATE_FILE
    config_path = get_config_path()

    if state_file.exists():
        raise RuntimeError(
            f"Graph-only mode state already exists at {state_file}. "
            "Exit graph-only mode first or remove the stale state file."
        )

    current_paths = [
        workspace / "memory" / "graph.json",
        workspace / "memory" / "HISTORY.md",
        workspace / "memory" / f"{date.today().isoformat()}.md",
        workspace / "memory" / "vectordb",
    ]
    return_backup_dir = _create_backup(workspace, current_paths)

    config_backup_path = state_root / GRAPH_ONLY_CONFIG_BACKUP
    previous_kg_enabled: bool | None = None
    if config_path.exists():
        shutil.copy2(config_path, config_backup_path)
        config_data = _read_json(config_path)
        previous_kg_enabled = bool(
            config_data.get("agents", {})
            .get("memoryFeatures", {})
            .get("knowledgeGraphEnabled", True)
        )

    restore_seed(workspace, restore_backup_dir)
    apply_seed(workspace, mode="graph-only")

    if config_path.exists():
        config_data = _read_json(config_path)
    else:
        config_data = {}
    config_data.setdefault("agents", {})
    config_data["agents"].setdefault("memoryFeatures", {})
    config_data["agents"]["memoryFeatures"]["knowledgeGraphEnabled"] = False
    config_path.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    state = {
        "active": True,
        "entered_at": datetime.now().isoformat(),
        "workspace": str(workspace),
        "restore_from_backup": str(restore_backup_dir),
        "return_backup_dir": str(return_backup_dir),
        "config_path": str(config_path),
        "config_backup_path": str(config_backup_path) if config_backup_path.exists() else "",
        "previous_knowledge_graph_enabled": previous_kg_enabled,
    }
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Graph-only fallback mode enabled for workspace: {workspace}")
    print(f"Return backup: {return_backup_dir}")
    print(f"State file: {state_file}")
    print("Next step: restart the Nanobot service before rerunning Scenario 2.")
    return 0


def exit_graph_only_mode(workspace: Path) -> int:
    state_file = _state_root(workspace) / GRAPH_ONLY_STATE_FILE
    if not state_file.exists():
        raise RuntimeError(f"Graph-only mode state file not found: {state_file}")

    state = _read_json(state_file)
    return_backup_dir = Path(state["return_backup_dir"]).expanduser().resolve()
    config_path = Path(state["config_path"]).expanduser().resolve()
    config_backup_path_str = state.get("config_backup_path") or ""
    config_backup_path = Path(config_backup_path_str).expanduser().resolve() if config_backup_path_str else None

    restore_seed(workspace, return_backup_dir)

    if config_backup_path and config_backup_path.exists():
        shutil.copy2(config_backup_path, config_path)
    elif config_path.exists():
        config_data = _read_json(config_path)
        config_data.setdefault("agents", {})
        config_data["agents"].setdefault("memoryFeatures", {})
        previous_kg_enabled = state.get("previous_knowledge_graph_enabled")
        if previous_kg_enabled is not None:
            config_data["agents"]["memoryFeatures"]["knowledgeGraphEnabled"] = bool(previous_kg_enabled)
            config_path.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        state_file.unlink()
    except OSError:
        pass

    print(f"Graph-only fallback mode disabled for workspace: {workspace}")
    print("Next step: restart the Nanobot service to resume the previous state.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed an architecture-focused Phase 67 manual test workspace.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply the Phase 67 architecture seed.")
    apply_parser.add_argument(
        "--workspace",
        default=str(Path.home() / ".nanobot" / "workspace"),
        help="Target Nanobot workspace path.",
    )
    apply_parser.add_argument(
        "--mode",
        choices=["full", "graph-only"],
        default="full",
        help="full = graph + memory/history seed; graph-only = graph seed only.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore from a previous backup.")
    restore_parser.add_argument(
        "--workspace",
        default=str(Path.home() / ".nanobot" / "workspace"),
        help="Target Nanobot workspace path.",
    )
    restore_parser.add_argument(
        "--backup-dir",
        required=True,
        help="Backup directory created by the apply command.",
    )

    enter_parser = subparsers.add_parser(
        "enter-graph-only-mode",
        help="Restore prior state, apply graph-only seed, and disable KG auto-injection.",
    )
    enter_parser.add_argument(
        "--workspace",
        default=str(Path.home() / ".nanobot" / "workspace"),
        help="Target Nanobot workspace path.",
    )
    enter_parser.add_argument(
        "--restore-from-backup",
        default="",
        help="Backup dir to restore before applying graph-only mode. Defaults to latest phase67 backup.",
    )

    exit_parser = subparsers.add_parser(
        "exit-graph-only-mode",
        help="Restore the pre-switch workspace/config captured by enter-graph-only-mode.",
    )
    exit_parser.add_argument(
        "--workspace",
        default=str(Path.home() / ".nanobot" / "workspace"),
        help="Target Nanobot workspace path.",
    )

    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()

    if args.command == "apply":
        return apply_seed(workspace, mode=args.mode)
    if args.command == "restore":
        return restore_seed(workspace, Path(args.backup_dir).expanduser().resolve())
    if args.command == "enter-graph-only-mode":
        restore_from_backup = None
        if args.restore_from_backup:
            restore_from_backup = Path(args.restore_from_backup).expanduser().resolve()
        return enter_graph_only_mode(workspace, restore_from_backup=restore_from_backup)
    return exit_graph_only_mode(workspace)


if __name__ == "__main__":
    raise SystemExit(main())
