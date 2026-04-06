@echo off
title Nanobot 绿化并轨启动程序 (Portable Auto-Launcher)
echo ---------------------------------------------------
echo 首次启动会自动构建国内镜像依赖环境并拉取模型，请确保网络畅通
echo ---------------------------------------------------

:: 设置临时环境变量防冲突，%~dp0 代表此 bat 所在目录
set BASE_DIR=%~dp0
set PYTHONPATH=%BASE_DIR%
set NANOBOT_HOME=%BASE_DIR%user_data

:: 黑魔法 1：全局 Pip 强制走清华大学源（光速下依赖）
set PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

:: 黑魔法 2：给 HuggingFace 换上纯净的国内镜像（免翻墙直连下载大模型权重）
set HF_ENDPOINT=https://hf-mirror.com
set HF_HOME=%BASE_DIR%models\huggingface_cache

:: 黑魔法 3：强行让无头浏览器内核下载走国内阿里镜像，并存在本地物理路径
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
set PLAYWRIGHT_BROWSERS_PATH=%BASE_DIR%browsers

echo 环境路径挂载完成，准备执行...

:: 智能感知：如果是已经集成的完全体（存在内置 runtime），则物理断网直连
if exist "%BASE_DIR%runtime\python.exe" (
    echo 【提示】已激活完全脱机的内嵌 Python (绿色版大环境)
    .\runtime\python.exe -m nanobot gateway
    pause
    exit /b
)

:: 容灾退化：如果没有内置 Python（仅源码包），尝试借助物理主机的 Python 构建
echo 【提示】未检测到离线 runtime 环境，尝试借助系统 Python 构建...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 您的电脑上没有安装 Python，且未提供免安装的 runtime 环境，无法启动。
    pause
    exit /b
)

:: 如果连 venv 都没建，帮你全自动搞定
if not exist "%BASE_DIR%.venv" (
    echo [构建] 正在为您创建全新的虚拟环境...
    python -m venv .venv
    echo [构建] 正在高速下载系统依赖，请耐心等待 (约需几分钟)...
    call .venv\Scripts\activate.bat
    pip install "uv>=0.5.0"
    uv pip install -r requirements.txt
    uv pip install fastapi uvicorn
    echo [构建] 正在高速下载无头浏览器内核...
    playwright install chromium
) else (
    call .venv\Scripts\activate.bat
)

echo [启动] 准备进入网关系统...
python -m nanobot gateway
pause
