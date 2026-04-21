import asyncio
import logging

# Set up logging to observe the output
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def run_manual_tests():
    try:
        from nanobot.agent.skills import execute_skill
        from nanobot.utils.exceptions import ToolValidationFailure, SkillLoadError
    except ImportError as e:
        logger.error(f"Cannot import nanobot modules. Ensure you are running this from the project root. {e}")
        return

    print("\n" + "="*50)
    print("🚀 启动 Phase 56 PSV 手动测试辅助脚本")
    print("="*50)

    # 场景 1: Happy Path
    print("\n▶️ 测试场景 1: 尝试执行合法的 'read' 动作...")
    try:
        # payload passed directly 
        result = await execute_skill("dummy_test_skill", "read", {})
        print("✅ 场景 1 成功！返回结果:", result)
    except Exception as e:
        print("❌ 场景 1 失败 (预期应成功放行):", repr(e))

    # 场景 2: 拦截非法动作 'write'
    print("\n▶️ 测试场景 2: 尝试执行非法的 'write' 动作...")
    try:
        result = await execute_skill("dummy_test_skill", "write", {"file": "secret.txt"})
        print("❌ 场景 2 失败 (预期应被拦截，但放行了)，返回结果:", result)
    except ToolValidationFailure as e:
        print(f"✅ 场景 2 成功！已成功拦截并抛出 ToolValidationFailure: {e}")
    except Exception as e:
        print(f"⚠️ 场景 2 出现了非预期的异常 (预期为 ToolValidationFailure): {repr(e)}")

    print("\n" + "="*50)
    print("🎉 基础通讯与拦截验证完成！")
    print("提示：如果想验证 AST 注入、Timeout 等其他场景，请手动修改 skills/dummy_test_skill/validator.py 代码后再次运行此脚本。")

if __name__ == "__main__":
    asyncio.run(run_manual_tests())
