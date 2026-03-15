"""
Router Agent 测试脚本

用法：
python test_router.py
"""

from nanobot.agent.router import SimpleRouter, RouterAgent


def test_simple_router():
    """测试简单路由器"""
    router = SimpleRouter()
    
    test_cases = [
        # 邮件相关
        ("帮我搜索上周的业绩报表邮件", "email_analysis"),
        ("搜索来自老板的邮件", "email_analysis"),
        ("分析邮件附件", "email_analysis"),
        ("查看 Outlook 邮件", "email_analysis"),
        
        # 搜索相关
        ("帮我搜索 Python 教程", "data_search"),
        ("查找最新的 AI 新闻", "data_search"),
        ("搜索一下这个错误怎么解决", "data_search"),
        
        # 任务执行
        ("帮我发送消息给张三", "task_execution"),
        ("执行这个命令", "task_execution"),
        ("创建一个新文件", "task_execution"),
        
        # 默认
        ("今天天气怎么样", "general"),
        ("你好吗", "general"),
        ("帮我算一下 1+1", "general"),
    ]
    
    print("=" * 60)
    print("SimpleRouter 测试")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for user_input, expected in test_cases:
        result = router.route(user_input)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} 输入: {user_input[:30]:<30} -> {result:<15} (期望: {expected})")
    
    print("-" * 60)
    print(f"结果: {passed}/{passed+failed} 通过")
    print()


def test_router_keywords():
    """测试路由器关键词"""
    router = SimpleRouter()
    
    print("=" * 60)
    print("关键词匹配测试")
    print("=" * 60)
    
    # 测试各种邮件相关关键词
    email_tests = [
        "邮件",
        "email", 
        "邮箱",
        "outlook",
        "附件",
        "发件人",
        "收件人",
        "搜索邮件",
        "查看邮件",
    ]
    
    for keyword in email_tests:
        result = router.route(keyword)
        print(f"  '{keyword}' -> {result}")
    
    print()


if __name__ == "__main__":
    test_simple_router()
    test_router_keywords()
    print("测试完成！")
