"""
预分析器 - Task Pre-Analyzer

职责：
1. 接收用户请求和任务类型
2. 查询知识库，判断是否有可复用的历史任务
3. 生成任务计划（是否可复用、需要哪些参数）
"""

from typing import Any
from loguru import logger

from nanobot.agent.task_knowledge import TaskKnowledgeStore
from nanobot.agent.task_tracker import TaskTracker, TaskStatus, Step


class TaskAnalysisResult:
    """任务分析结果"""
    
    def __init__(
        self,
        reusable: bool = False,
        source_task: dict = None,
        steps: list[str] = None,
        params_needed: dict = None,
        suggestion: str = "",
        confidence: float = 0.0,
    ):
        self.reusable = reusable
        self.source_task = source_task or {}
        self.steps = steps or []
        self.params_needed = params_needed or {}
        self.suggestion = suggestion
        self.confidence = confidence
    
    def to_dict(self) -> dict:
        return {
            "reusable": self.reusable,
            "source_task": self.source_task,
            "steps": self.steps,
            "params_needed": self.params_needed,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


class PreAnalyzer:
    """
    任务预分析器
    
    在执行任务前分析知识库，判断：
    1. 是否有相似的历史任务
    2. 任务状态（已完成/进行中/失败）
    3. 可复用的步骤
    4. 需要的新参数
    
    设计原则：
    - 优先使用知识库缓存
    - 但始终获取最新数据
    - 生成可执行的任务计划
    """
    
    def __init__(self, workspace, provider=None, model=None):
        self.workspace = workspace
        self.knowledge_store = TaskKnowledgeStore(workspace)
        self.task_tracker = TaskTracker(workspace)
        self.provider = provider
        self.model = model
    
    async def analyze(
        self, 
        user_request: str, 
        task_type: str = None,
    ) -> TaskAnalysisResult:
        """
        分析用户请求，返回任务计划
        
        流程：
        1. 用 LLM 提取任务关键描述（key）
        2. 与知识库中的 key 比较相似度
        3. 相似度 > 50% 询问用户，< 50% 判定不匹配
        
        Args:
            user_request: 用户原始请求
            task_type: 任务类型（来自 Router）
            
        Returns:
            TaskAnalysisResult: 包含是否可复用、历史任务、建议步骤等
        """
        logger.info(f"PreAnalyzer: 分析请求 - {user_request[:50]}")
        
        # 1. 获取知识库任务
        all_tasks = self.knowledge_store.get_all_tasks()
        
        if not all_tasks:
            logger.info("PreAnalyzer: 知识库为空，从头开始")
            return TaskAnalysisResult(
                reusable=False,
                suggestion="新任务，将从头开始执行"
            )
        
        # 2. 用 LLM 提取任务关键描述（作为 key）
        task_key = await self._extract_task_key(user_request)
        
        if not task_key:
            logger.info("PreAnalyzer: key 提取失败，从头开始")
            return TaskAnalysisResult(
                reusable=False,
                suggestion="新任务，将从头开始执行"
            )
        
        logger.info(f"PreAnalyzer: 提取 key = '{task_key}'")
        
        # 3. 与知识库中的 key 比较相似度
        best_match, similarity = self._search_by_key(task_key, all_tasks)
        
        logger.info(f"PreAnalyzer: 最佳匹配相似度 = {similarity:.2%}")
        
        # 4. 判定是否匹配（阈值 50%）
        if not best_match or similarity < 0.5:
            logger.info(f"PreAnalyzer: 相似度 {similarity:.2%} < 50%，判定不匹配，从头开始")
            return TaskAnalysisResult(
                reusable=False,
                suggestion="新任务，将从头开始执行"
            )
        
        # 5. 判断是否可以复用
        status = best_match.get("status", "completed")
        
        if status == "completed":
            steps = best_match.get("steps", [])
            use_count = best_match.get("use_count", 0)
            
            logger.info(f"PreAnalyzer: 相似度 {similarity:.2%} >= 50%，匹配成功 - key={best_match.get('key')}")
            
            return TaskAnalysisResult(
                reusable=True,
                source_task=best_match,
                steps=steps,
                params_needed={},
                suggestion=self._generate_suggestion(best_match, user_request),
                confidence=similarity,
            )
        
        elif status == "failed":
            logger.info(f"PreAnalyzer: 历史任务失败过，建议调整参数")
            return TaskAnalysisResult(
                reusable=False,
                source_task=best_match,
                suggestion="上次执行失败，建议调整参数后重试"
            )
        
        else:
            return TaskAnalysisResult(
                reusable=False,
                source_task=best_match,
                suggestion="任务正在进行中，请稍后再试"
            )
    
    async def _extract_task_key(self, user_request: str) -> str | None:
        """
        用 LLM 提取任务关键描述（不超过 50 汉字或 200 英文字符）
        作为任务的唯一标识 key
        """
        if not self.provider:
            return None
        
        # 检测语言
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in user_request)
        max_len = 50 if is_chinese else 200
        
        prompt = f"""请用不超过 {max_len} {"个汉字" if is_chinese else "个英文单词"} 概括以下用户请求的核心任务。

## 用户请求
{user_request}

## 要求
1. 只返回关键描述，不要解释
2. 不要包含时间（如"今天"、"昨天"）
3. 不要包含具体参数（如具体人名、邮箱地址）
4. 保持简洁，只描述核心动作和目标

## 示例
- "帮我分析 inbox/reporting 邮件" → "分析邮件"
- "搜索关于项目的文档" → "搜索文档"
- "对比 SHV 和 SZV 销售数据" → "对比销售数据"

只返回关键描述，不要其他内容："""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "你是一个任务概括专家。请用简洁的关键词概括用户请求的核心任务。"},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.3,  # 稍微高一点，让不同表达有机会归一化
                max_tokens=64,
            )
            
            content = response.content.strip()
            # 清理多余字符
            content = content.strip('"\n ')
            
            logger.info(f"PreAnalyzer: key 提取结果 = '{content}'")
            return content if content else None
            
        except Exception as e:
            logger.warning(f"PreAnalyzer: key 提取失败 - {e}")
            return None
    
    def _search_by_key(self, task_key: str, tasks: list[dict]) -> tuple[dict | None, float]:
        """
        用字符串相似度比较 task_key 与知识库中的 key
        
        Returns:
            (最佳匹配任务, 相似度)
        """
        if not tasks or not task_key:
            return None, 0.0
        
        best_match = None
        best_similarity = 0.0
        
        for task in tasks:
            stored_key = task.get("key", "")
            
            if not stored_key:
                continue
            
            # 计算相似度（简单版：包含关系 + 公共词）
            similarity = self._calculate_similarity(task_key, stored_key)
            
            logger.info(f"PreAnalyzer: 比较 '{task_key}' vs '{stored_key}' = {similarity:.2%}")
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = task
        
        return best_match, best_similarity
    
    def _calculate_similarity(self, key1: str, key2: str) -> float:
        """
        计算两个 key 的相似度
        
        算法：
        1. 如果完全相同，返回 1.0
        2. 如果一个包含另一个，长度比例作为相似度
        3. 否则计算公共词比例
        """
        k1 = key1.lower().strip()
        k2 = key2.lower().strip()
        
        # 完全相同
        if k1 == k2:
            return 1.0
        
        # 包含关系
        if k1 in k2:
            return len(k1) / len(k2)
        if k2 in k1:
            return len(k2) / len(k1)
        
        # 公共词计算
        words1 = set(k1.replace("_", " ").replace("-", " ").split())
        words2 = set(k2.replace("_", " ").replace("-", " ").split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        # Jaccard 相似度
        return len(intersection) / len(union)
    
    async def _llm_compare(self, user_request: str, similar_tasks: list[dict]) -> dict | None:
        """
        使用 LLM 判断用户请求与历史任务是否语义相似。
        
        Returns:
            如果相似，返回最佳匹配的任务；否则返回 None
        """
        if not similar_tasks:
            return None
        
        # 如果没有 provider，回退到关键词匹配
        if not self.provider:
            logger.warning("PreAnalyzer: No provider, falling back to keyword matching")
            return similar_tasks[0] if similar_tasks else None
        
        # 构建 prompt
        history_list = []
        for i, task in enumerate(similar_tasks[:3]):  # 只比较前3个
            key = task.get("key", "")
            desc = task.get("description", "")[:200]
            steps = task.get("steps", [])
            
            # 提取步骤名称
            step_names = []
            for s in steps[:5]:
                if isinstance(s, dict):
                    step_names.append(s.get("tool", ""))
                elif isinstance(s, str):
                    step_names.append(s)
            
            history_list.append(f"""{i+1}. Key: {key}
   Description: {desc}
   Steps: {", ".join(step_names) if step_names else "(无步骤)"}""")
        
        history_text = "\n".join(history_list)
        
        prompt = f"""请判断用户的当前请求与以下历史任务是否语义相似。

## 用户当前请求
{user_request}

## 历史任务候选
{history_text}

## 判断标准
- 语义相似 = 核心目标相同（如都是"分析邮件"、"搜索信息"、"发送邮件"）
- 即使时间不同（如"今天"vs"昨天"），只要任务目标相同也算相似
- **关键**：如果任务目标明显不同，则不算相似！
  - 例如："分析SHV" vs "对比SHV和SZV" → 目标不同（一个是分析，一个是对比）
  - 例如："搜索某人的邮件" vs "搜索某话题的邮件" → 目标不同
- 只有当用户请求和历史任务的**核心目标**相同时才算相似

## 输出格式
请返回 JSON 格式：
{{
  "similar": true/false,
  "best_match_index": 0-2 (如果不相似则返回 -1),
  "reason": "简要说明判断理由（特别是为什么判定为不相似）"
}}

只返回 JSON，不要其他内容："""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "你是一个语义相似度判断专家。请仔细比较用户请求和历史任务，判断它们的核心目标是否相同。"},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.1,  # 低温度，更确定性
                max_tokens=512,
            )
            
            content = response.content.strip()
            logger.info(f"LLM compare response: {content[:200]}")
            
            # 解析 JSON 响应
            import json_repair
            result = json_repair.loads(content)
            
            similar = result.get("similar", False)
            best_match_index = result.get("best_match_index", -1)
            reason = result.get("reason", "")
            
            logger.info(f"LLM compare result: similar={similar}, index={best_match_index}, reason={reason}")
            
            if similar and 0 <= best_match_index < len(similar_tasks):
                return similar_tasks[best_match_index]
            else:
                return None
            
        except Exception as e:
            logger.warning(f"LLM compare failed: {e}, falling back to keyword matching")
        
        # Fallback: 使用关键词匹配
        return similar_tasks[0] if similar_tasks else None
    
    def _search_similar_tasks(
        self, 
        user_request: str, 
        task_type: str = None,
    ) -> list[dict]:
        """
        搜索知识库中的相似任务
        
        只有匹配度达到阈值（>5）才返回结果
        """
        all_tasks = self.knowledge_store.get_all_tasks()
        
        if not all_tasks:
            return []
        
        # 按使用次数排序（优先推荐常用的）
        all_tasks.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        
        # 简单关键词匹配
        user_lower = user_request.lower()
        matched = []
        
        for task in all_tasks:
            key = task.get("key", "").lower()
            desc = task.get("description", "").lower()
            
            # 计算匹配度
            score = 0
            
            # 1. 精确匹配 key（最高优先级）
            if key == user_lower:
                score += 20
            elif key in user_lower and len(key) > 5:
                score += 10
            elif user_lower in key and len(user_lower) > 5:
                score += 10
            
            # 2. 描述匹配
            if desc and len(desc) > 5:
                # 检查描述中的关键词是否在用户请求中
                desc_words = [w for w in desc.split() if len(w) > 3]
                matches = sum(1 for w in desc_words if w in user_lower)
                if matches > 0:
                    score += matches * 3
            
            # 3. task_type 匹配（较低优先级）
            if task_type and task.get("key", "").startswith(task_type):
                # 只有当分数已经>5时才加分
                if score > 0:
                    score += 2
            
            # 4. 工具步骤相似度（如果有保存的步骤）
            steps = task.get("steps", [])
            if steps:
                # 检查是否涉及相同的工具
                step_tools = set()
                for s in steps:
                    if isinstance(s, dict):
                        step_tools.add(s.get("tool", ""))
                    elif isinstance(s, str):
                        step_tools.add(s)
                
                # 检查用户请求是否提到相关工具
                relevant_tools = {"outlook", "email", "attachment", "message", "search", "analyze"}
                if step_tools & relevant_tools:  # 有交集
                    # 用户请求中有相关工具关键词
                    if any(t in user_lower for t in relevant_tools):
                        score += 5
            
            # 只有分数 > 5 才认为是相似任务
            if score > 5:
                matched.append((score, task))
        
        # 按分数排序
        matched.sort(key=lambda x: x[0], reverse=True)
        
        return [t for _, t in matched[:3]]
    
    def _extract_params(self, user_request: str) -> dict:
        """
        从用户请求中提取参数
        
        这是一个简单的实现，后续可以加入 LLM 提取
        """
        params = {}
        user_lower = user_request.lower()
        
        # 时间参数
        if "上周" in user_request:
            params["date_range"] = "last_week"
        elif "本周" in user_request:
            params["date_range"] = "this_week"
        elif "今天" in user_request:
            params["date_range"] = "today"
        elif "昨天" in user_request:
            params["date_range"] = "yesterday"
        
        # 文件夹
        if "收件箱" in user_request or "inbox" in user_lower:
            params["folder"] = "inbox"
        elif "已发送" in user_request or "sent" in user_lower:
            params["folder"] = "sent"
        
        # 发件人
        if "来自" in user_request:
            idx = user_request.find("来自")
            parts = user_request[idx+2:].split()
            if parts:
                params["sender"] = parts[0].rstrip(",，。")
        
        return params
    
    def _generate_suggestion(self, source_task: dict, user_request: str) -> str:
        """生成任务建议"""
        key = source_task.get("key", "")
        steps = source_task.get("steps", [])
        use_count = source_task.get("use_count", 0)
        
        suggestion = f"发现相似任务「{key}」"
        
        if use_count > 0:
            suggestion += f"，已成功使用 {use_count} 次"
        
        suggestion += "。可复用步骤："
        
        # 处理步骤列表（可能是字符串或字典）
        step_names = []
        for step in steps[:3]:
            if isinstance(step, dict):
                step_names.append(step.get("tool", "unknown"))
            elif isinstance(step, str):
                step_names.append(step)
        
        suggestion += " → ".join(step_names)
        
        if len(steps) > 3:
            suggestion += " → ..."
        
        return suggestion
    
    async def create_task_from_analysis(
        self,
        user_request: str,
        analysis: TaskAnalysisResult,
    ) -> str:
        """
        根据分析结果创建任务追踪
        
        Returns:
            task_id
        """
        if not analysis.reusable:
            # 新任务
            task_id = self.task_tracker.create_task(
                key="new_task",
                user_request=user_request,
            )
        else:
            # 基于历史任务
            key = analysis.source_task.get("key", "reused_task")
            task_id = self.task_tracker.create_task(
                key=key,
                user_request=user_request,
                analyzed_from=analysis.source_task.get("key", ""),
            )
            
            # 添加步骤
            steps = [
                Step(i+1, step_name, step_name, "")
                for i, step_name in enumerate(analysis.steps)
            ]
            self.task_tracker.add_steps(task_id, steps)
        
        return task_id
