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
    DESTRUCTIVE        = auto()  # 高破坏性操作（删除、格式化）
    UNTRUSTED_EXTERNAL = auto()  # 未经审计的外部插件或 MCP 工具
    
    # 组合快捷方式（HITL & L1 判断基准）
    # NOTE: SHELL_EXECUTION 本身不是高危判定——exec 执行 `dir` 等查询指令是合法的。
    # 高危判定由 ExecTool.evaluate_dynamic_tags() 在运行时检测高危命令模式后
    # 动态追加 DESTRUCTIVE 实现，而非在静态标签层一刀切。
    IS_HIGH_RISK = DESTRUCTIVE | UNTRUSTED_EXTERNAL


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
