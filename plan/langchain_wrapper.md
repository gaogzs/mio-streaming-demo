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

## 状态

- [x] ModelProvider实现
- [x] StreamingPipeline实现
- [x] LLMWrapper实现
