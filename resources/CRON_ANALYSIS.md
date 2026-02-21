# Cron Service 问题分析与统一调度器设计

## 一、Cron 为何不工作 - 根因分析

### 问题 1: Timer 在没有 job 时不启动

**位置**: `nanobot/cron/service.py` - `_arm_timer()`

```python
def _arm_timer(self) -> None:
    next_wake = self._get_next_wake_ms()
    if not next_wake or not self._running:
        return  # ❌ 如果没有 job，timer 永远不会启动！
```

**问题**: 如果 cron jobs 列表为空，定时器不会启动。但即使用户添加了 job，可能因为其他原因导致 jobs 没有被正确加载。

### 问题 2: CLI cron 命令没有调用 start()

**位置**: `nanobot/cli/commands.py` - cron 命令组

```python
# cron add/list/remove 等命令
service = CronService(store_path)  # 创建实例
job = service.add_job(...)         # 添加 job
# ❌ 没有调用 service.start()!
```

**影响**: 
- 通过 CLI 添加的 job 会保存到文件
- 但如果不重启 gateway，新 job 不会被加载到内存
- 因为 `_load_store()` 只在第一次访问时加载

### 问题 3: Gateway 启动后添加的 job

**场景**: 
1. 启动 gateway (没有 cron jobs)
2. 使用 `nanobot cron add` 添加 job
3. 问题：gateway 进程中的 CronService 实例不知道新 job 存在

**原因**: 
- 每个 CLI 命令创建新的 CronService 实例
- 每个实例有自己的内存缓存
- Gateway 进程和 CLI 进程不共享内存

### 问题 4: Jobs 文件路径问题

**位置**: `commands.py`

```python
cron_store_path = get_data_dir() / "cron" / "jobs.json"
```

可能的问题:
- `get_data_dir()` 返回的路径不正确
- 文件权限问题
- JSON 格式错误

---

## 二、统一调度器设计方案

### 目标
将三个独立的定时机制整合到一个统一的调度器中：
1. **CronService** - 定时执行 jobs
2. **HeartbeatService** - 定期检查任务
3. **AgentLoop** - 消息处理（虽然不是定时，但可以统一管理）

### 设计原则
- **单一事件循环**: 避免多个 timer 相互干扰
- **故障隔离**: 一个组件失败不影响其他组件
- **可观测性**: 统一的日志和状态监控

### 方案 A: 调度器模式 (推荐)

```python
class SchedulerService:
    """统一的调度服务"""
    
    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._main_task: asyncio.Task | None = None
    
    def schedule_cron(self, job_id: str, next_run_ms: int, callback):
        """注册 cron job"""
        self._tasks[job_id] = ScheduledTask(
            name=job_id,
            next_run_ms=next_run_ms,
            callback=callback,
            task_type="cron"
        )
    
    def schedule_heartbeat(self, interval_s: int, callback):
        """注册 heartbeat"""
        self._tasks["heartbeat"] = ScheduledTask(
            name="heartbeat",
            interval_s=interval_s,
            callback=callback,
            task_type="heartbeat"
        )
    
    async def start(self):
        """启动统一调度器"""
        self._running = True
        self._main_task = asyncio.create_task(self._run_loop())
    
    async def _run_loop(self):
        """主循环 - 每秒检查一次所有任务"""
        while self._running:
            now_ms = int(time.time() * 1000)
            
            for task in self._tasks.values():
                if task.should_run(now_ms):
                    try:
                        await task.execute()
                    except Exception as e:
                        logger.error(f"Task {task.name} failed: {e}")
            
            await asyncio.sleep(1)  # 每秒检查
```

### 方案 B: 事件驱动模式

使用 asyncio.Event 进行更精细的控制：

```python
class SchedulerService:
    def __init__(self):
        self._events: dict[str, asyncio.Event] = {}
    
    def schedule(self, name: str, delay_s: float):
        event = asyncio.Event()
        self._events[name] = event
        
        async def wait_and_fire():
            while self._running:
                await asyncio.sleep(delay_s)
                event.set()
                event.clear()
        
        asyncio.create_task(wait_and_fire(name))
    
    async def wait(self, name: str):
        await self._events[name].wait()
```

---

## 三、修复建议

### 立即可用的修复

1. **在 CLI cron 命令中添加 reload 逻辑**
   ```python
   # cron add 命令后通知 gateway 重新加载
   # 或者在 gateway 中定期检查 jobs.json 变化
   ```

2. **修复 CronService 的空 job 问题**
   ```python
   # 即使没有 job，也保持 timer 运行
   # 定期检查是否有新 job
   ```

3. **添加启动时的 job 验证日志**
   ```python
   async def start(self):
       self._load_store()
       logger.info(f"Cron started with {len(self._store.jobs)} jobs")
       for job in self._store.jobs:
           logger.info(f"  - {job.name}: {job.schedule}")
   ```

### 长期改进

1. 实现统一调度器
2. 添加进程间通信（如果需要从 CLI 通知 gateway）
3. 添加健康检查和自动恢复

---

## 四、调试步骤

### 验证 Cron 是否工作

1. 添加一个每 10 秒运行的测试 job:
   ```bash
   nanobot cron add -n "test" -m "hello" -e 10
   ```

2. 重启 gateway:
   ```bash
   nanobot gateway
   ```

3. 查看日志，确认:
   - "Cron started with X jobs"
   - "Cron: executing job 'test'"

4. 如果不工作，检查:
   - `nanobot cron list` - 确认 job 存在
   - `nanobot status` - 查看配置

---

*本文档持续更新...*
