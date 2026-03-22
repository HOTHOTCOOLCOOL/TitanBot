#!/usr/bin/env python3
"""
简化版的测试脚本，用于验证本地LLM的基本功能和函数调用兼容性。
"""

from openai import OpenAI
import json

# 配置本地LLM
LOCAL_LLM_CONFIG = {
    "base_url": "http://10.18.34.60:5888/v1",
    "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
    "api_key": None,
}

# 配置OpenAI客户端
api_key = LOCAL_LLM_CONFIG["api_key"] if LOCAL_LLM_CONFIG["api_key"] else "not-needed"
client = OpenAI(api_key=api_key, base_url=LOCAL_LLM_CONFIG["base_url"])

print("=" * 60)
print("本地LLM功能测试")
print("=" * 60)

# 测试1: 基本聊天功能
print("\n[测试1] 基本聊天功能")
try:
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],
        messages=[
            {"role": "system", "content": "你是一个测试助手，请用中文回复。"},
            {"role": "user", "content": "请回复'测试成功'。"}
        ],
        max_tokens=50,
        temperature=0.1
    )
    print(f"✓ 基本聊天成功")
    print(f"  响应: {response.choices[0].message.content}")
except Exception as e:
    print(f"✗ 基本聊天失败: {type(e).__name__}: {e}")

# 测试2: 检查API支持的功能
print("\n[测试2] 检查API支持的功能")
try:
    # 尝试获取模型列表
    models = client.models.list()
    print(f"✓ 获取到 {len(list(models))} 个模型")
    
    # 检查第一个模型的详细信息
    for model in models:
        print(f"  模型: {model.id}")
        break
except Exception as e:
    print(f"✗ 获取模型列表失败: {type(e).__name__}: {e}")

# 测试3: 简化函数调用测试
print("\n[测试3] 简化函数调用测试")
functions = [
    {
        "name": "get_weather",
        "description": "获取天气信息",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "城市名称"}
            },
            "required": ["location"]
        }
    }
]

messages = [{"role": "user", "content": "北京天气怎么样？"}]

try:
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],
        messages=messages,
        functions=functions,
        function_call="auto",
        max_tokens=100
    )
    
    message = response.choices[0].message
    print(f"✓ API调用成功")
    
    if hasattr(message, 'function_call') and message.function_call:
        print(f"  函数调用: {message.function_call.name}")
        print(f"  参数: {message.function_call.arguments}")
    else:
        print(f"  直接回复: {message.content}")
        
except Exception as e:
    print(f"✗ 函数调用测试失败: {type(e).__name__}: {e}")
    print(f"  错误详情: {e}")

# 测试4: 使用tools参数（新的OpenAI API格式）
print("\n[测试4] 使用tools参数（新格式）")
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"}
                },
                "required": ["location"]
            }
        }
    }
]

messages = [{"role": "user", "content": "上海天气怎么样？"}]

try:
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=100
    )
    
    message = response.choices[0].message
    print(f"✓ Tools API调用成功")
    
    if hasattr(message, 'tool_calls') and message.tool_calls:
        print(f"  工具调用数量: {len(message.tool_calls)}")
        for tool_call in message.tool_calls:
            print(f"  工具: {tool_call.function.name}")
            print(f"  参数: {tool_call.function.arguments}")
    elif hasattr(message, 'content'):
        print(f"  直接回复: {message.content}")
        
except Exception as e:
    print(f"✗ Tools API测试失败: {type(e).__name__}: {e}")
    print(f"  注意: 可能本地LLM不支持tools参数")

# 测试5: 测试邮件处理函数的特定格式
print("\n[测试5] 邮件处理函数测试")
mail_functions = [
    {
        "name": "process_emails_attachments",
        "description": "查找邮件中的附件，解析并分析内容，然后将分析结果保存并发送邮件",
        "parameters": {
            "type": "object",
            "properties": {
                "subject_contains": {"type": "string", "description": "邮件主题包含的关键词（可选）"},
                "recipient_email": {"type": "string", "description": "接收分析结果的邮箱地址（必填）"}
            },
            "required": ["recipient_email"]
        }
    }
]

messages = [{"role": "user", "content": "帮我查找主题包含'Weekly Summary Report'的邮件，把附件摘要发到 DAVIDMSN@HOTMAIL.COM"}]

try:
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],
        messages=messages,
        functions=mail_functions,
        function_call={"name": "process_emails_attachments"},  # 强制调用特定函数
        max_tokens=100
    )
    
    message = response.choices[0].message
    print(f"✓ 邮件函数调用成功")
    
    if hasattr(message, 'function_call') and message.function_call:
        print(f"  调用函数: {message.function_call.name}")
        try:
            args = json.loads(message.function_call.arguments)
            print(f"  参数解析: {args}")
        except:
            print(f"  参数原始: {message.function_call.arguments}")
    else:
        print(f"  直接回复: {message.content}")
        
except Exception as e:
    print(f"✗ 邮件函数测试失败: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n建议:")
print("1. 如果函数调用失败，可能是本地LLM不完全支持OpenAI的函数调用功能")
print("2. 可以尝试使用简化版的函数定义")
print("3. 或者直接让模型输出JSON格式的参数，然后手动解析")
print("4. 检查本地LLM服务的文档，了解其函数调用支持情况")