# Nanobot 演进全景对比

> 从一个简单的聊天机器人到企业级 AI Agent 框架的蜕变之路  
> 最后更新: 2026-04-03

---

## 工程规模对比

| 维度 | 🐣 初始 NanoBot | 🚀 当前 Nanobot | 增幅 |
|------|----------------|----------------|------|
| **核心源文件** | ~10 | **105** | **×10.5** |
| **测试文件** | 0 | **87** | 0 → 87 |
| **测试用例** | 0 | **1271+ passed** | 0 → 1271+ |
| **子包 (packages)** | 2 (`agent`, `config`) | **14** | **×7** |
| **内置工具 (Tools)** | 3 (shell, outlook, exec) | **19** | **×6.3** |
| **通道适配器 (Channels)** | 2 (CLI, MoChat) | **9** | **×4.5** |
| **Phase 迭代** | — | **41 个大阶段** | — |
| **论文参考** | 0 | **12** (AutoSkill, XSKILL, mem9, MemGPT, AI Memory Survey, MDER-DR, IndexRAG, OPENDEV, Dual-Tree, QChunker, OpenClaw-RL, BubbleRAG) | — |

---

## 架构演进全景图

```mermaid
graph TB
    subgraph BEFORE["🐣 初始 NanoBot"]
        direction TB
        B_LOOP["loop.py<br/>单文件 ~916 行<br/>所有逻辑混在一起"]
        B_KB["knowledge_workflow.py<br/>简单关键词匹配"]
        B_MEM["memory.py<br/>单文件 MEMORY.md"]
        B_TOOLS["3 个工具<br/>Shell / Outlook / Exec"]
        B_CH["2 个通道<br/>CLI / MoChat"]
        B_CFG["config.py<br/>简单配置"]

        B_LOOP --> B_KB
        B_LOOP --> B_MEM
        B_LOOP --> B_TOOLS
        B_LOOP --> B_CH
        B_LOOP --> B_CFG
    end

    subgraph AFTER["🚀 当前 Nanobot"]
        direction TB
        A_CORE["Agent Core<br/>loop.py + 12 拆分模块"]
        A_KNOW["知识系统<br/>5 层混合检索"]
        A_MEM["记忆架构<br/>7 层智能记忆"]
        A_TOOLS["19 个内置工具"]
        A_CH["9 个通道 + Gateway"]
        A_SEC["安全体系<br/>32 项审计修复"]
        A_DASH["Web Dashboard<br/>实时监控"]
        A_RPA["RPA 视觉层<br/>UIA + OCR + YOLO"]
        A_BUS["Event Bus<br/>异步解耦"]
        A_CRON["Cron 调度<br/>容错 + 通知"]

        A_CORE --> A_KNOW
        A_CORE --> A_MEM
        A_CORE --> A_TOOLS
        A_CORE --> A_CH
        A_CORE --> A_SEC
        A_CORE --> A_DASH
        A_CORE --> A_RPA
        A_CORE --> A_BUS
        A_CORE --> A_CRON
    end

    BEFORE -.->|"41 Phase 演进"| AFTER

    style BEFORE fill:#2d2d2d,color:#ccc,stroke:#555
    style AFTER fill:#1a1a2e,color:#eee,stroke:#0f3460
```

---

## 历史演进归档

随着项目复杂度的增加，早期的全景演进和 Phase 更新日志已经被分类归档：

- [Epoch 1: Phase 1-20 演进回顾与架构对比](./EVOLUTION_epoch1_20.md)
- [Epoch 2: Phase 21-32 详细迭代历程](./EVOLUTION_epoch21_32.md)
- [Epoch 3: Phase 33-41 洋葱架构与安全降级纪元](./EVOLUTION_epoch33_41.md)

## 最新阶段核心内容 (Phase 42及以后)

有关当前开发进度和 Phase 42 及之后的迭代内容，请以此为唯一事实来源 (Single Source of Truth)：
- [Nanobot 开发进度与 Roadmap](../../progress_report.md)

> Note: 有关架构安全、最佳实践与具体开发规范，请参阅根目录 `docs/` 下的其他详细文档。
