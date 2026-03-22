from openai import OpenAI
import json
import os
from mail_skill import process_emails_attachments

# 配置本地LLM
LOCAL_LLM_CONFIG = {
    "base_url": "http://10.18.34.60:5888/v1",
    "model": "nvidia.nvidia-nemotron-3-super-120b-a12b",
    "api_key": None,  # 本地LLM通常不需要API key
    "context_length": 190000
}

# 配置OpenAI客户端 - 使用正确的API key处理
api_key = LOCAL_LLM_CONFIG["api_key"] if LOCAL_LLM_CONFIG["api_key"] else "not-needed"
client = OpenAI(api_key=api_key, base_url=LOCAL_LLM_CONFIG["base_url"])

# 使用tools参数（新格式）而不是functions参数
tools = [
    {
        "type": "function",
        "function": {
            "name": "process_emails_attachments",
            "description": "查找邮件中的附件，解析并分析内容，然后将分析结果保存并发送邮件",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject_contains": {"type": "string", "description": "邮件主题包含的关键词（可选）"},
                    "from_email": {"type": "string", "description": "发件人邮箱包含的字符串（可选）"},
                    "analysis_type": {"type": "string", "enum": ["summary", "keywords", "full"], "default": "summary"},
                    "recipient_email": {"type": "string", "description": "接收分析结果的邮箱地址（必填）"}
                },
                "required": ["recipient_email"]
            }
        }
    }
]

# 模拟对话
messages = [{"role": "user", "content": "帮我查找主题包含'Weekly Summary Report - Week 6 2026'的邮件，把附件摘要发到 DAVIDMSN@HOTMAIL.COM"}]

print(f"使用本地LLM: {LOCAL_LLM_CONFIG['base_url']}")
print(f"模型: {LOCAL_LLM_CONFIG['model']}")
print("尝试使用tools参数进行函数调用...")

try:
    # 首先尝试使用tools参数
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    print("✓ 使用tools参数调用成功")
    
    message = response.choices[0].message
    tool_calls = message.tool_calls if hasattr(message, 'tool_calls') else []
    
    if tool_calls:
        print(f"✓ 模型调用了 {len(tool_calls)} 个工具")
        for tool_call in tool_calls:
            if tool_call.function.name == "process_emails_attachments":
                arguments = json.loads(tool_call.function.arguments)
                print(f"  参数: {arguments}")
                
                # 调用本地函数
                result = process_emails_attachments(**arguments)
                print(f"  本地函数调用结果: {result[:100]}...")
                
                # 将结果返回给模型
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": result
                })
                
                # 获取模型的最终回复
                try:
                    second_response = client.chat.completions.create(
                        model=LOCAL_LLM_CONFIG["model"],
                        messages=messages
                    )
                    if second_response.choices[0].message.content:
                        print(f"最终回复: {second_response.choices[0].message.content}")
                    else:
                        print("✓ 处理完成")
                except Exception as e:
                    print(f"第二次API调用失败: {e}")
                    print(f"处理结果: {result}")
    else:
        print(f"模型没有调用工具，直接回复: {message.content}")
        
except Exception as e:
    print(f"tools参数调用失败: {e}")
    print("尝试简化方法：直接调用邮件处理函数...")
    
    # 如果函数调用失败，直接调用邮件处理函数
    try:
        result = process_emails_attachments(
            subject_contains="Weekly Summary Report",
            recipient_email="DAVIDMSN@HOTMAIL.COM"
        )
        print(f"✓ 直接调用邮件处理函数成功: {result[:200]}")
    except Exception as e2:
        print(f"邮件处理函数也失败: {e2}")
        print("请检查Outlook和邮件处理相关依赖")

print("\n备选方案说明:")
print("1. 如果函数调用导致模型崩溃，可以考虑使用Prompt Engineering让模型输出JSON参数")
print("2. 或者直接使用预定义的参数调用邮件处理函数")
print("3. 检查本地LLM服务的文档，了解其函数调用支持情况")