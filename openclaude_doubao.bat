@echo off
title OpenClaude - Doubao (Volcengine)
set CLAUDE_CODE_USE_OPENAI=1
set OPENAI_API_KEY=f3b097ea-cc2e-42d6-aabb-2d0f22862f8c
set OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
set OPENAI_MODEL=doubao-seed-2-0-pro-260215

echo ==============================================
echo 启动 OpenClaude (当前使用默认大模型: %OPENAI_MODEL%)
echo ==============================================

openclaude
