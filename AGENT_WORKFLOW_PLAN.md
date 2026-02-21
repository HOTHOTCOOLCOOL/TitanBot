# 智能任务执行工作流程规划

## 🎯 核心理念

用户给 nanobot 一个任务时，应该有以下智能流程：

```
用户任务 → 知识库预分析 → 任务规划 → 执行 → 知识沉淀 → 未来复用
```

---

## 📋 当前状态

### 已有基础
- task_memory: 简单的 key-value 存储
- task_knowledge.py: 基本的 CRUD
- loop.py: idle checker + 记忆整合

### 缺失能力
- ❌ 任务预分析（是否有知识可复用）
- ❌ 任务状态追踪（进行中/已完成/失败）
- ❌ 执行中增量更新
- ❌ 知识沉淀自动化

---

## 🔄 新工作流程设计

### 阶段 1: 任务预分析（Task Pre-Analyzer）

**目标**：收到任务时，先查知识库，判断如何处理

```
用户: "帮我分析上周的业绩报表邮件"

nanobot 内部流程:
1. 调用 task_memory.search("业绩报表")
2. 找到历史任务:
   - key: "weekly_report_analysis"
   - status: "completed"
   - last_run: "2026-02-14"
   - steps: ["search_emails", "analyze_attachments", "generate_summary"]
   - params: {"folder": "inbox/reporting", "date_range": "last_week"}
3. 判断:
   - ✅ 相似任务存在，可复用步骤
   - ⚠️ 参数可能不同，需要调整
   - ⏰ 上次是2周前，可能需要更新数据
4. 输出计划:
   "找到相似任务「周报分析」，步骤可复用。需要：
   - 更新日期参数（上周）
   - 重新获取最新邮件
   - 复用分析逻辑"
```

**实现方案**：
```python
class TaskPreAnalyzer:
    def analyze(self, user_task: str) -> TaskAnalysisResult:
        # 1. 语义搜索知识库
        similar = self.knowledge.search_similar(user_task)
        
        # 2. 判断状态
        for task in similar:
            if task.status == "completed":
                return TaskAnalysisResult(
                    reusable=True,
                    source_task=task,
                    steps=task.steps,
                    params_needed=self._extract_params(user_task),
                    suggestion=f"可复用「{task.key}」的步骤"
                )
        
        return TaskAnalysisResult(reusable=False, steps=[])
```

---

### 阶段 2: 任务状态追踪（Task State Machine）

**目标**：追踪每个任务的生命周期

```
任务状态机：
- created    → 刚创建
- planning   → 规划中（分析知识库）
- running    → 执行中
- pending_review → 等待用户确认
- completed  → 完成
- failed     → 失败
- cancelled  → 取消
```

**存储结构扩展**：
```python
class TrackedTask:
    task_id: str
    key: str  # 任务类型标识
    user_request: str  # 用户原始请求
    status: TaskStatus
    
    # 规划阶段
    analyzed_from: str  # 基于哪个历史任务
    steps: list[Step]
    params: dict
    
    # 执行阶段
    current_step: int
    step_results: list[StepResult]
    
    # 完成阶段
    result_summary: str
    knowledge_to_save: dict
    created_at: datetime
    updated_at: datetime
```

---

### 阶段 3: 执行中增量更新（Incremental Updates）

**目标**：执行过程中实时更新知识库

```
场景：用户让 nanobot 分析 100 封邮件

当前流程（一次性）：
1. 获取所有邮件
2. 分析所有
3. 全部完成后才保存

改进流程（增量）：
1. 获取前 10 封
2. 分析 → 部分结果
3. ⚡ 保存中间结果到知识库
4. 继续处理下 10 封
5. ...
6. 最终整合全部结果
7. 保存完整知识

好处：
- 如果中断，保留已有结果
- 用户可随时查询进度
- 支持长任务恢复
```

---

### 阶段 4: 知识沉淀自动化（Auto-Knowledge Distillation）

**目标**：任务完成后自动构建可复用知识

```
当前（手动）：
1. 用户确认"收到"
2. 调用 task_memory.save()
3. 手动填写信息

改进（自动）：
任务完成后自动提取：
1. 任务类型（key）
2. 执行步骤（steps）
3. 参数模式（params schema）
4. 结果摘要（result_summary）
5. 关键教训（lessons_learned）

保存到知识库，无需用户手动确认
（除非用户明确要求不保存）
```

---

## 🛠️ 实施路径

### Step 1: 任务状态机（基础）
```
优先级：P0
时间：1-2天

实现：
1. 创建 TaskState enum
2. 创建 TaskTracker 类
3. 修改 task_memory 工具支持状态
4. 添加 status 查询功能
```

### Step 2: 预分析器（核心）
```
优先级：P0
时间：2-3天

实现：
1. TaskPreAnalyzer 类
2. 语义搜索（简单关键词匹配起步）
3. 任务相似度判断
4. 生成任务规划建议
5. 集成到 loop.py 入口
```

### Step 3: 增量更新（进阶）
```
优先级：P1
时间：3-5天

实现：
1. 中间结果存储
2. 断点续传支持
3. 进度查询 API
4. 长任务分片机制
```

### Step 4: 自动沉淀（完善）
```
优先级：P1
时间：2-3天

实现：
1. LLM 自动提取知识
2. 知识质量评估
3. 自动保存逻辑
4. 用户确认可选
```

---

## 📊 预期效果

### 优化前
```
用户: "分析业绩报表"
→ nanobot: 不知道以前做过类似任务
→ 从零开始执行
→ 完成后手动保存
→ 下次同类任务: 重复全部工作
```

### 优化后
```
用户: "分析业绩报表"
→ nanobot: 查知识库，找到"周报分析"任务
→ "发现相似任务「周报分析」，可复用步骤：
   - 搜索邮件 ✓
   - 分析附件 ✓
   - 只需更新参数（日期）"
→ 执行（复用 70% 步骤）
→ 自动保存新知识
→ 下次同类任务: 复用 90%
```

---

## 🔧 技术要点

1. **知识库 Schema 升级**
   - 添加 status 字段
   - 添加 steps 详情
   - 添加 params_schema
   - 添加 execution_history

2. **LLM 参与**
   - 任务分类（classification）
   - 参数提取（extraction）
   - 知识摘要（summarization）
   - 相似度判断（similarity）

3. **数据一致性**
   - 事务性保存
   - 版本控制
   - 回滚机制
