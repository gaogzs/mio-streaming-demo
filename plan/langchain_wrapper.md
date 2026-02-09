# langchain_wrapper 模块计划

## 模块职责

封装 LangChain 调用，提供可切换的模型源和统一的调用接口。

## 文件结构

```
langchain_wrapper/
├── __init__.py       # 模块导出
├── model_provider.py # ModelType枚举 + ModelProvider类
├── pipeline.py       # StreamingPipeline (ChatPromptTemplate + 前后处理)
└── wrapper.py        # LLMWrapper简单封装
```

## 核心类

### ModelProvider

提供可切换的模型源。

```python
class ModelType(Enum):
  OPENAI = "openai"
  ANTHROPIC = "anthropic"
  LOCAL_QWEN = "local_qwen"

class ModelProvider:
  def get_model(model_type, model_name) -> BaseChatModel
```

支持的模型源:
- OpenAI API (gpt-4o, gpt-4o-mini等)
- Anthropic API (claude-3等)
- 本地Qwen (通过vllm兼容OpenAI接口)

### StreamingPipeline

LangChain管道封装。

```python
class StreamingPipeline:
  def __init__(model, system_prompt)
  def invoke(input_text, history) -> str
  async def ainvoke(input_text, history) -> str
```

### LLMWrapper

对外简单接口，组合 ModelProvider 和 StreamingPipeline。

```python
class LLMWrapper:
  def __init__(model_type, model_name, persona)
  def chat(user_input, history) -> str
  async def achat(user_input, history) -> str
```

### MemoryStore（memory 子模块）

RAG 长期记忆模块，基于 Chroma 向量数据库 + HuggingFace 中文嵌入模型。

#### 文件结构

```
langchain_wrapper/
└── memory/
    ├── __init__.py     # 模块导出
    ├── category.py     # MemoryCategory 枚举
    ├── store.py        # MemoryStore 核心类（Chroma + HuggingFace）
    ├── retriever.py    # MemoryRetriever LCEL 包装器
    └── formatter.py    # 记忆格式化工具
```

#### API

```python
from langchain_wrapper.memory import (
  MemoryStore, MemoryCategory, MemoryRetriever,
  format_memories, format_memories_compact,
)

# 创建存储
store = MemoryStore()  # 默认持久化到 data/memory_store/

# 添加记忆
memory_id = store.add_memory("用户喜欢打篮球", MemoryCategory.USER_PREFERENCE)

# 批量添加
ids = store.add_memories(
  ["喜欢看NBA", "讨论过总决赛"],
  [MemoryCategory.USER_PREFERENCE, MemoryCategory.TOPIC],
)

# 检索（语义相似度）
results = store.retrieve("运动爱好", top_k=3)
print(format_memories(results))
# 【相关记忆】
# - [用户偏好] 用户喜欢打篮球 (2026-02-08 14:23)

# LCEL 集成（未来使用）
retriever = MemoryRetriever(store, top_k=3)
runnable = retriever.as_runnable()
# 在管道中：| retriever.as_runnable() |
```

## 状态

- [x] ModelProvider实现
- [x] StreamingPipeline实现
- [x] LLMWrapper实现
- [x] MemoryStore 记忆模块实现
