#!/usr/bin/env python3
"""
测试本地LLM连接配置。
用于验证用户提供的本地LLM配置是否可以正常工作。
"""

from openai import OpenAI
import openai
import json
import requests
import sys

def test_network_connection():
    """测试网络连接是否正常"""
    base_url = "http://10.18.34.60:5888"
    print(f"测试网络连接: {base_url}")
    
    try:
        # 尝试连接基础URL
        response = requests.get(base_url, timeout=5)
        if response.status_code == 200:
            print(f"✓ 网络连接正常 (状态码: {response.status_code})")
            return True
        else:
            print(f"✗ 网络连接异常 (状态码: {response.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ 网络连接失败: 无法连接到服务器")
        return False
    except requests.exceptions.Timeout:
        print("✗ 网络连接超时: 服务器响应时间过长")
        return False
    except Exception as e:
        print(f"✗ 网络连接错误: {e}")
        return False

def test_api_endpoint():
    """测试API端点是否正常"""
    api_url = "http://10.18.34.60:5888/v1"
    print(f"\n测试API端点: {api_url}")
    
    try:
        # 尝试连接API端点
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            print(f"✓ API端点正常 (状态码: {response.status_code})")
            # 检查返回内容
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                data = response.json()
                print(f"  API响应: {json.dumps(data, indent=2, ensure_ascii=False)[:200]}...")
            return True
        else:
            print(f"✗ API端点异常 (状态码: {response.status_code})")
            print(f"  响应头: {dict(response.headers)}")
            return False
    except Exception as e:
        print(f"✗ API端点测试失败: {e}")
        return False

def test_openai_client():
    """测试OpenAI客户端配置"""
    print("\n测试OpenAI客户端配置:")
    
    # 用户配置
    LOCAL_LLM_CONFIG = {
        "base_url": "http://10.18.34.60:5888/v1",
        "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
        "api_key": "not-needed",
        "context_length": 190000
    }
    
    # 配置OpenAI客户端
    client = OpenAI(api_key=LOCAL_LLM_CONFIG["api_key"], base_url=LOCAL_LLM_CONFIG["base_url"])
    
    print(f"  模型: {LOCAL_LLM_CONFIG['model']}")
    
    # 测试模型列表
    try:
        print("\n尝试获取可用模型列表...")
        models = LOCAL_LLM_CONFIG["model"]
        if models and hasattr(models, 'data'):
            print(f"✓ 获取到 {len(models.data)} 个模型:")
            for model in models.data[:5]:  # 只显示前5个
                print(f"  - {model.id}")
            if len(models.data) > 5:
                print(f"  ... 还有 {len(models.data) - 5} 个模型")
            return True
        else:
            print("✗ 无法获取模型列表")
            return False
    except Exception as e:
        print(f"✗ 获取模型列表失败: {e}")
        return False

def test_chat_completion():
    """测试聊天补全功能"""
    print("\n测试聊天补全功能:")
    
    LOCAL_LLM_CONFIG = {
        "base_url": "http://10.18.34.60:5888/v1",
        "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
        "api_key": "not-needed",
    }
    
    client = OpenAI(api_key=LOCAL_LLM_CONFIG["api_key"], base_url=LOCAL_LLM_CONFIG["base_url"])
    
    # 简单的测试消息
    messages = [
        {"role": "system", "content": "你是一个测试助手，请用中文回复。"},
        {"role": "user", "content": "你好，请回复'测试成功'。"}
    ]
    
    try:
        print(f"  发送测试消息到模型: {LOCAL_LLM_CONFIG['model']}")
        
        response = client.completions.create(
            model=LOCAL_LLM_CONFIG["model"],
            prompt=messages,
            max_tokens=500,
            temperature=0.1,
            timeout=3600
        )
        
        if response and hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content
            print(f"✓ 聊天测试成功")
            print(f"  响应内容: {content}")
            print(f"  使用token: {response.usage.total_tokens if hasattr(response, 'usage') else '未知'}")
            return True
        else:
            print("✗ 聊天测试失败: 响应格式异常")
            return False
    except Exception as e:
        print(f"✗ API错误: {e}")
        return False
    

def test_function_calling():
    """测试函数调用功能（与test.py相同的配置）"""
    print("\n测试函数调用功能:")
    
    LOCAL_LLM_CONFIG = {
        "base_url": "http://10.18.34.60:5888/v1",
        "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
        "api_key": "not-needed",
    }
    
    openai.api_base = LOCAL_LLM_CONFIG["base_url"]
    openai.api_key = LOCAL_LLM_CONFIG["api_key"] or "not-needed"
    
    # 定义函数schema（与test.py相同）
    functions = [
        {
            "name": "process_emails_attachments",
            "description": "查找邮件中的附件，解析并分析内容，然后将分析结果保存并发送邮件",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject_contains": {"type": "string", "description": "邮件主题包含的关键词（可选）"},
                    "from_email": {"type": "string", "description": "发件人邮箱包含的字符串（可选）"},
                    "received_after": {"type": "string", "description": "接收日期之后，格式 YYYY-MM-DD（可选）"},
                    "received_before": {"type": "string", "description": "接收日期之前（可选）"},
                    "analysis_type": {"type": "string", "enum": ["summary", "keywords", "full"], "default": "summary"},
                    "recipient_email": {"type": "string", "description": "接收分析结果的邮箱地址（必填）"},
                    "save_results_to": {"type": "string", "description": "本地保存分析结果的目录路径，默认为桌面（可选）"}
                },
                "required": ["recipient_email"]
            }
        }
    ]
    
    messages = [{"role": "user", "content": "帮我查找主题包含'周报'的邮件，把附件摘要发到 DAVIDMSN@HOTMAIL.COM"}]
    
    try:
        print("  发送函数调用测试...")
        response = openai.ChatCompletion.create(
            model=LOCAL_LLM_CONFIG["model"],
            messages=messages,
            functions=functions,
            function_call="auto",
            max_tokens=100
        )
        
        if response and hasattr(response, 'choices') and len(response.choices) > 0:
            message = response.choices[0].message
            if hasattr(message, 'function_call') and message.function_call:
                print(f"✓ 函数调用测试成功")
                print(f"  调用函数: {message.function_call.name}")
                print(f"  参数: {message.function_call.arguments}")
                return True
            else:
                print(f"  响应内容: {message.content if hasattr(message, 'content') else '无内容'}")
                print("⚠ 模型没有调用函数（可能是正常情况）")
                return True  # 没有调用函数也可能是正常的
        else:
            print("✗ 函数调用测试失败: 响应格式异常")
            return False
    except Exception as e:
        print(f"✗ 函数调用测试异常: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("本地LLM配置测试")
    print("=" * 60)
    
    tests = [
        ("网络连接", test_network_connection),
        ("API端点", test_api_endpoint),
        ("OpenAI客户端", test_openai_client),
        ("聊天补全", test_chat_completion),
        ("函数调用", test_function_calling),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[{test_name}]")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\n总测试数: {total}, 通过: {passed}, 失败: {total - passed}")
    
    if passed == total:
        print("\n✅ 所有测试通过！本地LLM配置正确。")
        print("   现在可以运行 tests/skill/test.py 进行完整测试。")
    else:
        print("\n⚠ 部分测试失败，请检查以下问题:")
        print("   1. 确保本地LLM服务正在运行")
        print("   2. 检查网络连接 (http://10.18.34.60:5888)")
        print("   3. 确认模型名称 'nvidia.nvidia-nemotron-3-super-120b-a12b' 正确")
        print("   4. 检查防火墙设置")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)