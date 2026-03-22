# Nanobot 改进计划

## 已完成的分析

### 项目优势
1. **架构清晰** - 模块化设计，职责分离明确
2. **代码质量高** - 使用现代Python特性（类型注解、async/await、Pydantic）
3. **文档完善** - README.md 详细，包含多个集成示例
4. **扩展性好** - Provider Registry 机制设计优雅，易于添加新供应商
5. **安全性考虑** - 包含workspace限制、用户白名单等安全功能

### 识别出的改进点

#### 1. 代码质量改进
- [x] **工具参数验证** - 增加null值处理（已完成）
- [x] **日志框架统一** - litellm_provider 切换到 loguru，移除调试文件 dump
- [x] **错误处理优化** - bare except 替换为具体异常类型
- [ ] **类型提示完善** - 部分函数缺少完整类型注解
- [ ] **文档字符串标准化** - 统一docstring格式

#### 2. 测试改进
- [x] **增加测试覆盖率** - 新增 46 个测试 (config, session, provider)
- [x] **配置验证测试** - test_config_schema.py (15 tests)
- [x] **工具执行测试** - test_provider_parse.py (12 tests)
- [x] **集成测试** - test_session_manager.py (14 tests)

#### 3. 性能优化
- [x] **内存使用优化** - SessionManager LRU 缓存限制 (maxsize=128)
- [x] **缓存机制** - Config 实例缓存，避免重复解析
- [x] **LLM Token 追踪** - metrics.py 新增 record_tokens()，/stats 展示 token 汇总
- [x] **LLM 调用重试** - litellm_provider.py 指数退避重试（最多 2 次），仅对超时/5xx/连接错误
- [ ] **并发处理** - 优化异步任务调度

#### 4. 可维护性改进
- [ ] **配置管理** - 环境变量与配置文件优先级处理
- [x] **日志结构化** - LLM 和 Tool 执行结构化计时日志
- [x] **监控指标** - metrics.py 性能指标收集器
- [x] **核心解耦** - `loop.py` 拆解，抽出 `MemoryManager` 与 `CommandHandler`
- [x] **死代码清理** - 删除未引用方法 `_execute_from_knowledge`/`_extract_tool_args_from_history`
- [x] **常量提取** - 内联硬编码常量提取到模块级 (`_WAIT_PHRASES` 等 4 组)

#### 5. 功能增强
- [ ] **工具增强** - 添加更多内置工具（数据库查询、API调用等）
- [ ] **技能管理** - 技能安装、更新、卸载流程
- [ ] **插件系统** - 支持第三方插件扩展

#### 6. 记忆系统增强（mem9 启发）
- [x] **Session End Hook** — `/new` 时自动保存会话摘要到 daily log
- [x] **统一 Memory CRUD 工具** — `memory` 工具支持 store/search/delete 三种 action
- [x] **记忆意图检测** — 识别"记住"/"remember" 等触发词，自动提示 LLM 使用 memory 工具
- [x] **标签过滤** — 记忆条目支持 tags，搜索时可按 tag 过滤
- [x] **记忆导入/导出** — `/memory export` 和 `/memory import` 命令
- [x] **记忆策略注入** — system prompt 中注入"什么该记 / 什么不该记"指导

#### 7. 知识系统升级（AutoSkill + XSKILL 论文启发）
- [ ] **结构化知识表示** — TaskEntry 新增 triggers/tags/description/anti_patterns/confidence 字段
- [ ] **混合检索 (Dense+BM25)** — 引入 Dense embedding + BM25 加权检索，替代纯 jieba+Jaccard
- [ ] **Experience 双流设计** — 新增 Experience Bank (动作级战术提示)，与 Skill 互补
- [ ] **Management Judge** — add/merge/discard 三分决策，控制知识库质量
- [ ] **Query Rewriting** — 检索前查询改写，解决多轮对话指代消解
- [ ] **检索后适配** — 检索到知识后裁剪适配当前上下文再注入

## 实施计划

### 第一阶段：代码质量与测试（高优先级）
1. 完善类型提示和文档字符串
2. 添加配置文件验证测试
3. 增加工具执行单元测试
4. 添加异常处理测试

### 第二阶段：性能与可维护性（中优先级）
1. 优化内存使用，检查潜在泄露
2. 实现结构化日志
3. 添加基础性能监控
4. 优化配置加载性能

### 第三阶段：知识系统升级 + 功能增强（高优先级 — Phase 12-14）
1. 结构化知识表示增强 (triggers/tags/description)
2. Dense+BM25 混合检索替代纯文本匹配
3. Experience Bank 双流设计
4. Knowledge Management Judge
5. Query Rewriting + 检索后适配
6. 工程卫生（根目录清理、loop.py 模块化、类型提示）

### 第四阶段：功能扩展（低优先级）
1. 扩展工具集
2. 完善技能管理系统
3. 设计插件架构

## 预期收益

### 短期（1-2周）
- 提高代码可靠性和可维护性
- 减少潜在bug
- 提高开发效率

### 中期（1-2个月）
- 提高系统稳定性
- 增强调试能力
- 改善用户体验

### 长期（3-6个月）
- 支持更大规模部署
- 扩展生态系统
- 吸引更多贡献者

## 风险评估

### 技术风险
- **低风险**: 类型提示和测试改进
- **中风险**: 性能优化可能引入bug
- **高风险**: 架构重构可能破坏兼容性

### 缓解措施
1. 逐步实施，每个阶段完成后进行测试
2. 保持向后兼容性
3. 充分测试后再合并到主分支

## 成功标准

### 量化指标
1. 测试覆盖率从<20%提升到>80%
2. 类型提示覆盖率从70%提升到95%
3. 启动时间减少20%
4. 内存使用减少15%

### 质化指标
1. 代码审查通过率提高
2. 贡献者体验改善
3. 用户反馈积极

## 资源需求

### 开发资源
- 主要开发者：2-3人周
- 测试资源：1-2人周
- 文档更新：1人周

### 工具支持
- 静态分析工具：mypy, ruff
- 测试框架：pytest, pytest-asyncio
- 性能分析：cProfile, memory_profiler

---

*本计划将根据实际实施情况动态调整*