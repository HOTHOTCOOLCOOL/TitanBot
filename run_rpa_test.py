import subprocess
import sys

def main():
    print("🚀 初始化 RPA (视觉多模态) 测试...")
    
    # 1. 确保 rpa-demo-skill 已加载 (强制刷新以获取最新 SKILL.md)
    print("📦 加载 rpa-demo-skill 技能...")
    import shutil
    from pathlib import Path
    workspace_skills = Path.home() / ".nanobot" / "workspace" / "skills" / "rpa-demo-skill"
    if workspace_skills.exists():
        shutil.rmtree(workspace_skills)
    workspace_skills.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree("resources/rpa-demo-skill", workspace_skills)
    
    # 2. 调用 Agent 执行
    print("\n🤖 启动 Agent 执行计算器点击任务 (1 + 1 = 2)...")
    print("请不要移动鼠标，观察 Agent 的自动操作。")
    print("-" * 50)
    
    # 使用 ui_name 的 prompt — 引导 LLM 按名称点击按钮
    prompt = (
        "Run the calculator RPA demo. But note: instead of 5+8, I want you to calculate 1+1=2. "
        "Use the rpa tool's ui_name parameter to click buttons by name: "
        "rpa({\"action\": \"click\", \"ui_name\": \"One\"}) for the digit 1, "
        "rpa({\"action\": \"click\", \"ui_name\": \"Plus\"}) for +, "
        "rpa({\"action\": \"click\", \"ui_name\": \"Equals\"}) for =. "
        "Remember to first open calc.exe, wait, then screen_capture with annotate_ui=true, "
        "then click the buttons using ui_name."
    )
    
    # 启动 agent 单轮执行
    subprocess.run([sys.executable, "-m", "nanobot", "agent", "--logs", "-m", prompt])
    
    print("-" * 50)
    print("✅ 测试脚本执行完毕。")

if __name__ == "__main__":
    main()
