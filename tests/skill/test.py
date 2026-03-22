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

# 定义函数schema
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

# 模拟对话
messages = [{"role": "user", "content": "帮我查找主题包含'Weekly Summary Report'的邮件，把附件摘要发到 DAVIDMSN@HOTMAIL.COM"}]

# 注意：需要设置OpenAI API密钥或使用兼容的API
# import os
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"

print(f"使用本地LLM: {LOCAL_LLM_CONFIG['base_url']}")
print(f"模型: {LOCAL_LLM_CONFIG['model']}")

try:
    response = client.chat.completions.create(
        model=LOCAL_LLM_CONFIG["model"],  # 使用用户配置的模型
        messages=messages,
        functions=functions,
        function_call="auto"
    )
except Exception as e:
    print(f"API调用失败: {e}")
    print(f"请检查：1. 网络连接 (URL: {LOCAL_LLM_CONFIG['base_url']}) 2. 模型名称: {LOCAL_LLM_CONFIG['model']}")
    exit(1)

message = response.choices[0].message
# 检查是否有function_call
if hasattr(message, 'function_call') and message.function_call:
    function_name = message.function_call.name
    arguments = json.loads(message.function_call.arguments)
    # 调用本地函数
    result = process_emails_attachments(**arguments)
    # 将结果返回给模型
    messages.append({
        "role": "assistant",
        "content": None,
        "function_call": {
            "name": function_name,
            "arguments": message.function_call.arguments
        }
    })
    messages.append({
        "role": "function",
        "name": function_name,
        "content": result
    })
    try:
        second_response = client.chat.completions.create(
            model=LOCAL_LLM_CONFIG["model"],  # 使用相同的本地模型
            messages=messages,
            functions=functions,
        )
        if second_response.choices[0].message.content:
            print(second_response.choices[0].message.content)
        else:
            print("第二次调用完成，无文本内容")
    except Exception as e:
        print(f"第二次API调用失败: {e}")
        print("本地函数调用结果:", result[:200])
else:
    print(f"模型没有调用函数，直接回复: {message.content}")
