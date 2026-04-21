from enum import Flag, auto
from dataclasses import dataclass

class CapabilityTag(Flag):
    NONE = 0
    
    # 数据与系统交互流向
    DATA_READ          = auto()  # 读取本地/工作区数据
    DATA_WRITE         = auto()  # 写入本地/工作区数据
    INFO_RETRIEVAL     = auto()  # 外部检索（web_search, outlook.search, ssrs等）
    SYS_COMMUNICATION  = auto()  # 向外发送人类通知（send_email, message等）
    
    # 敏感执行能力
    SHELL_EXECUTION    = auto()  # 执行 OS Shell 命令或脚本
    CODE_EVALUATION    = auto()  # 在沙箱中求值代码（hooks.py, Python snippets）
    
    # 风险维度
    MUTATIVE           = auto()  # 产生可持久化的状态变更副作用
    SENSITIVE          = auto()  # 高危但可经人类审批放行的操作（→ HITL 软拦截路径）
                                 # 例如：RPA 系统级热键、config 注入的邮件审批场景
                                 # 由 evaluate_dynamic_tags() 动态评定，或由 capability_overrides 注入
    DESTRUCTIVE        = auto()  # 毁灭性操作，永不批准（→ L1 R-DESTRUCTIVE-GUARD 硬阻断）
                                 # 例如：rm -rf、python -c 代码注入、fork bomb
    UNTRUSTED_EXTERNAL = auto()  # 未经审计的外部插件或 MCP 工具
    
    # 组合快捷方式（HITL & L1 判断基准）
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │ 三档分类语义 (ADR-61):                                              │
    # │  PERMIT   → 直接执行（无任何标签触发，或仅 MUTATIVE / DATA_WRITE）  │
    # │  HITL     → 软拦截：HITLMiddleware 暂停并等待人工 Approve/Reject    │
    # │             触发条件: effective_tags & IS_HIGH_RISK                 │
    # │  L1 HARD  → 硬阻断：R-DESTRUCTIVE-GUARD 直接返回错误，永不执行     │
    # │             触发条件: effective_tags & DESTRUCTIVE                  │
    # │                                                                     │
    # │ DESTRUCTIVE 纳入 IS_HIGH_RISK 的理由：当 L1 因 registry=None 等    │
    # │ 边缘原因失效时，HITL 作为第二道防线来兜底捕获 DESTRUCTIVE 操作。   │
    # └─────────────────────────────────────────────────────────────────────┘
    IS_HIGH_RISK = SENSITIVE | DESTRUCTIVE | UNTRUSTED_EXTERNAL


@dataclass
class ExecutionPolicy:
    """
    工具/技能级执行策略约束（仅声明可实际执行的边界）。
    
    注意：python_allow_network 仅对 PythonSandbox 中的 hooks.py 有效，
    通过 sys.addaudithook 拦截 socket.connect 实现。
    ShellSandbox 中的 exec 命令无法在 Python 层阻止网络访问。
    """
    timeout_seconds: int = 120
    python_allow_network: bool = False   # 仅 PythonSandbox 有效
    workspace_dir_restrict: bool = True  # PythonSandbox file path audit
