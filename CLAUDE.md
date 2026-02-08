# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

mio-streaming-demo 是一个虚拟直播间 LLM wrapper 项目，让 LLM 扮演虚拟主播与观众互动。使用 Python + LangChain 构建。

## 开发命令

```bash
# 激活虚拟环境
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 测试命令行聊天 (待实现)
python -m streaming_studio.test_chatter_studio

# 测试 WebSocket 服务 (待实现)
python -m connection.test_chatter_web
```

## 架构设计

```
langchain_wrapper/    # LLM 交互层：模型源切换(OpenAI API/本地Qwen)、LangChain管道、对外wrapper
streaming_studio/     # 虚拟直播间：异步运行、send_comment()接收弹幕、get_response()返回回复、本地数据库存储弹幕
connection/           # WebSocket层：StreamServiceHost服务、支持多输入者/输出者订阅
prompts/              # 提示词文件(.txt)：基础指令、人物预设(3个)
secrets/              # API密钥等敏感信息(gitignore)
plan/                 # 工作计划文档
spec/                 # 项目规范(只读，不要修改)
```

## 编码规范

- 命名：snake_case
- 缩进：2空格
- 注释/文档：中文
- 所有路径以项目根目录为基准

## 当前阶段

草稿阶段：搭建框架，代码简洁可读，不考虑生产环境部署需求。
