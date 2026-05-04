# Task

- [ ] T01 新增 `nanobot/agent/harness/` lite-only 辅助层，覆盖 repo root 解析、job 元数据读写、Artifact 脚手架与 launcher 模板。
- [ ] T02 实现基于 Artifact 文件现状的阶段派生与 ready 检查，并把 `state.json` 固定为诊断快照而非真相源。
- [ ] T03 将 `nanobot harness start/status/advance` 接入 `nanobot/cli/commands.py` 的 `Typer` 主入口，并确保 `--mode heavy` 显式拒绝。
- [ ] T04 新增 A1/A2 测试：验证 lite 路径落盘、heavy 拒绝、输出 launcher 路径一致，以及实现面明确 lite-only。
- [ ] T05 新增 A3/A4 测试：验证 `evidence_gate.md` 结构不全时 not ready / blocked，以及 start/advance launcher 的 exact-output 契约。
- [ ] T06 新增 A5/A6 测试：覆盖 repo 根、子目录、repo 外、repo/workspace 分离四类 root 解析，以及 stale `state.json` 重算刷新。
- [ ] T07 运行靶向 pytest 回归，并将命令、结果、任务覆盖情况写回 `codex_result.md`。
