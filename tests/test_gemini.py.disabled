
import os
from google import genai

# ==========================================
# 1. 代理设置 (保持你的本地代理配置)
# ==========================================
PROXY_URL = "http://127.0.0.1:51903" # 确保这里是你的代理端口
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL
os.environ["ALL_PROXY"] = PROXY_URL

# ==========================================
# 2. 初始化新版 Client
# ==========================================
API_KEY = "AIzaSyChc" # 替换为你的真实 API Key

# 新版 SDK 使用 Client 对象来管理连接
client = genai.Client(api_key=API_KEY)

try:
    print("正在通过代理连接 Gemini API (使用新版 SDK)...")
    
    # ==========================================
    # 3. 发起请求
    # 注意：新版的方法名是 client.models.generate_content
    # 参数名也变成了 model 和 contents
    # ==========================================
    response = client.models.generate_content(
        model='gemini-2.5-flash', # 这里使用最新的 Flash 模型名称
        contents='你好，请确认你是否收到这条消息？'
    )
    
    print("\n✅ --- 测试成功 ---")
    print(f"Gemini 回复: {response.text}")
    
except Exception as e:
    print("\n❌ --- 测试失败 ---")
    print(f"错误信息: {e}")