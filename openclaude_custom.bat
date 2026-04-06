@echo off
title OpenClaude - Local Custom Proxy
set CLAUDE_CODE_USE_OPENAI=1
set OPENAI_API_KEY=None
set OPENAI_BASE_URL=http://10.18.34.60:5888/v1
set OPENAI_MODEL=minimax-m2.5-mlx

echo ==============================================
echo 启动 OpenClaude (使用内网自定义服务: %OPENAI_MODEL%)
echo ==============================================

openclaude
