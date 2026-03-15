"""
综合测试脚本 - 测试 Router, Task Tracker, PreAnalyzer, Knowledge Distiller

用法：
python test_agent_features.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def test_router():
    """测试 Router 任务路由"""
    print("=" * 60)
    print("1. 测试 Router (任务路由)")
    print("=" * 60)
    
    from nanobot.agent.router import SimpleRouter
    
    router = SimpleRouter()
    
    test_cases = [
        # 邮件相关
        ("帮我搜索上周的业绩报表邮件", "email_analysis"),
        ("搜索来自老板的邮件", "email_analysis"),
        ("查看 Outlook 邮件", "email_analysis"),
        
        # 搜索相关
        ("帮我搜索 Python 教程", "data_search"),
        ("查找最新的 AI 新闻", "data_search"),
        
        # 任务执行
        ("帮我发送消息给张三", "task_execution"),
        ("执行这个命令", "task_execution"),
        
        # 默认
        ("今天天气怎么样", "general"),
        ("你好吗", "general"),
    ]
    
    passed = 0
    for user_input, expected in test_cases:
        result = router.route(user_input)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        print(f"{status} {user_input[:25]:<25} -> {result}")
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过\n")
    return passed == len(test_cases)


def test_task_tracker():
    """测试 Task Tracker 任务追踪"""
    print("=" * 60)
    print("2. 测试 Task Tracker (任务追踪)")
    print("=" * 60)
    
    import tempfile
    from nanobot.agent.task_tracker import TaskTracker, TaskStatus, Step
    
    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        tracker = TaskTracker(workspace)
        
        # 1. 创建任务
        task_id = tracker.create_task(
            key="email_analysis",
            user_request="帮我分析上周的业绩报表邮件",
        )
        print(f"✓ 创建任务: {task_id}")
        
        # 2. 获取活跃任务
        task = tracker.get_active_task()
        assert task is not None, "获取活跃任务失败"
        print(f"✓ 活跃任务: {task.key}, 状态: {task.status.value}")
        
        # 3. 添加步骤
        steps = [
            Step(1, "search_emails", "搜索邮件", "outlook.search_emails"),
            Step(2, "analyze_attachments", "分析附件", "attachment_analyzer"),
            Step(3, "generate_summary", "生成摘要", ""),
        ]
        tracker.add_steps(task_id, steps)
        print(f"✓ 添加了 {len(steps)} 个步骤")
        
        # 4. 更新状态
        tracker.update_status(task_id, TaskStatus.RUNNING)
        task = tracker.get_task(task_id)
        assert task.status == TaskStatus.RUNNING
        print(f"✓ 状态更新为: {task.status.value}")
        
        # 5. 更新步骤
        tracker.update_step(task_id, 0, status="completed", result="找到 10 封邮件")
        tracker.update_step(task_id, 1, status="completed", result="分析了 5 个附件")
        print("✓ 步骤 1,2 完成")
        
        # 6. 增量保存
        tracker.save_intermediate_result(
            task_id, "search_emails", "找到 10 封邮件", 
            {"emails": ["email1", "email2"]}
        )
        print("✓ 增量保存中间结果")
        
        # 7. 获取进度
        progress = tracker.get_progress(task_id)
        print(f"✓ 进度: {progress['completed_steps']}/{progress['total_steps']} ({progress['progress_percent']}%)")
        
        # 8. 完成任务
        tracker.complete_task(
            task_id,
            result_summary="完成！分析了 10 封邮件",
            knowledge_to_save={"key": "weekly_report", "steps": ["search_emails"]}
        )
        task = tracker.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        print(f"✓ 任务完成，状态: {task.status.value}")
        
        # 9. 获取历史
        history = tracker.get_task_history(key="email_analysis")
        print(f"✓ 历史记录: {len(history)} 条")
    
    print("\n结果: 全部通过 ✓\n")
    return True


def test_task_knowledge():
    """测试 Task Knowledge 知识库"""
    print("=" * 60)
    print("3. 测试 Task Knowledge (知识库)")
    print("=" * 60)
    
    import tempfile
    from nanobot.agent.task_knowledge import TaskKnowledgeStore
    
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = TaskKnowledgeStore(workspace)
        
        # 1. 添加任务
        store.add_task(
            key="weekly_report",
            description="每周业绩报表分析",
            steps=["search_emails", "analyze_attachments", "generate_summary"],
            params={"folder": "inbox"},
            result_summary="分析完成"
        )
        print("✓ 添加任务: weekly_report")
        
        # 2. 查找任务
        task = store.find_task("weekly_report")
        assert task is not None, "查找任务失败"
        print(f"✓ 找到任务: {task['key']}, 步骤: {task['steps']}")
        
        # 3. 更新使用次数（通过更新任务来增加计数）
        store.update_task("weekly_report", "测试更新")
        store.update_task("weekly_report", "再次测试更新")
        task = store.find_task("weekly_report")
        print(f"✓ 使用次数: {task['use_count']}")
        
        # 4. 获取所有任务
        all_tasks = store.get_all_tasks()
        print(f"✓ 总任务数: {len(all_tasks)}")
        
        # 5. 搜索任务
        results = store.search_tasks("报表")
        print(f"✓ 搜索 '报表': {len(results)} 条结果")
    
    print("\n结果: 全部通过 ✓\n")
    return True


def test_pre_analyzer():
    """测试 PreAnalyzer 预分析器"""
    print("=" * 60)
    print("4. 测试 PreAnalyzer (预分析器)")
    print("=" * 60)
    
    import tempfile
    from nanobot.agent.pre_analyzer import PreAnalyzer
    from nanobot.agent.task_knowledge import TaskKnowledgeStore
    
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # 先添加一些测试数据
        store = TaskKnowledgeStore(workspace)
        store.add_task(
            key="email_weekly_report",
            description="每周业绩报表邮件分析",
            steps=["search_emails", "analyze_attachments", "generate_summary"],
            params={"folder": "inbox"},
            result_summary="完成"
        )
        store.update_task("email_weekly_report", "更新1")
        store.update_task("email_weekly_report", "更新2")
        print("✓ 添加测试数据到知识库")
        
        # 测试 PreAnalyzer
        analyzer = PreAnalyzer(workspace)
        
        # 测试分析
        result = asyncio.run(analyzer.analyze(
            "帮我分析上周的业绩报表邮件",
            task_type="email_analysis"
        ))
        
        print(f"✓ 分析结果:")
        print(f"  - 可复用: {result.reusable}")
        print(f"  - 匹配任务: {result.source_task.get('key', 'N/A')}")
        print(f"  - 建议: {result.suggestion[:50]}...")
        print(f"  - 置信度: {result.confidence}")
    
    print("\n结果: 全部通过 ✓\n")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Agent Features 综合测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 1. Router
    try:
        results.append(("Router", test_router()))
    except Exception as e:
        print(f"✗ Router 测试失败: {e}\n")
        results.append(("Router", False))
    
    # 2. Task Tracker
    try:
        results.append(("Task Tracker", test_task_tracker()))
    except Exception as e:
        print(f"✗ Task Tracker 测试失败: {e}\n")
        results.append(("Task Tracker", False))
    
    # 3. Task Knowledge
    try:
        results.append(("Task Knowledge", test_task_knowledge()))
    except Exception as e:
        print(f"✗ Task Knowledge 测试失败: {e}\n")
        results.append(("Task Knowledge", False))
    
    # 4. PreAnalyzer
    try:
        results.append(("PreAnalyzer", test_pre_analyzer()))
    except Exception as e:
        print(f"✗ PreAnalyzer 测试失败: {e}\n")
        results.append(("PreAnalyzer", False))
    
    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 全部测试通过!")
    else:
        print("⚠️ 部分测试失败，请检查")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
