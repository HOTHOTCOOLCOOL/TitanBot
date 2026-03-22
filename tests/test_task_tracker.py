"""
Task Tracker 测试脚本

用法：
python test_task_tracker.py
"""

from pathlib import Path
from nanobot.agent.task_tracker import TaskTracker, TaskStatus, Step


def test_task_tracker():
    """测试任务追踪器"""
    # 使用临时目录
    workspace = Path("test_workspace")
    workspace.mkdir(exist_ok=True)
    
    tracker = TaskTracker(workspace)
    
    print("=" * 60)
    print("TaskTracker 测试")
    print("=" * 60)
    
    # 1. 创建任务
    print("\n1. 创建任务...")
    task_id = tracker.create_task(
        key="email_analysis",
        user_request="帮我分析上周的业绩报表邮件",
        analyzed_from="weekly_report_v1"
    )
    print(f"   创建任务: {task_id}")
    
    # 2. 获取活跃任务
    print("\n2. 获取活跃任务...")
    task = tracker.get_active_task()
    print(f"   任务: {task.key}")
    print(f"   状态: {task.status.value}")
    print(f"   基于: {task.analyzed_from}")
    
    # 3. 添加步骤
    print("\n3. 添加步骤...")
    steps = [
        Step(1, "search_emails", "搜索邮件", "outlook.search_emails"),
        Step(2, "analyze_attachments", "分析附件", "attachment_analyzer"),
        Step(3, "generate_summary", "生成摘要", ""),
    ]
    tracker.add_steps(task_id, steps)
    print(f"   添加了 {len(steps)} 个步骤")
    
    # 4. 更新状态为运行中
    print("\n4. 更新状态为 RUNNING...")
    tracker.update_status(task_id, TaskStatus.RUNNING)
    task = tracker.get_task(task_id)
    print(f"   状态: {task.status.value}")
    
    # 5. 更新步骤状态
    print("\n5. 更新步骤...")
    tracker.update_step(task_id, 0, status="completed", result="找到 10 封邮件")
    tracker.update_step(task_id, 1, status="completed", result="分析了 5 个附件")
    tracker.update_step(task_id, 2, status="running")
    print("   步骤 1,2 完成，步骤 3 进行中")
    
    # 6. 完成任务
    print("\n6. 完成任务...")
    tracker.complete_task(
        task_id,
        result_summary="完成！分析了 10 封邮件，生成了周报摘要",
        knowledge_to_save={
            "key": "weekly_report",
            "steps": ["search_emails", "analyze_attachments", "generate_summary"],
            "params": {"folder": "inbox/reporting"}
        }
    )
    task = tracker.get_task(task_id)
    print(f"   状态: {task.status.value}")
    print(f"   结果: {task.result_summary[:50]}...")
    
    # 7. 获取任务历史
    print("\n7. 获取任务历史...")
    history = tracker.get_task_history(key="email_analysis")
    print(f"   历史记录: {len(history)} 条")
    
    # 8. 列出所有任务
    print("\n8. 列出所有任务...")
    all_tasks = tracker.list_tasks()
    print(f"   总任务数: {len(all_tasks)}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    test_task_tracker()
