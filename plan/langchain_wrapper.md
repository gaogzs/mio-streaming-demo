# langchain_wrapper 模块计划

## 模块职责

封装 LangChain 调用，提供可切换的模型源和统一的调用接口。

## 文件结构

```
langchain_wrapper/
├── __init__.py       # 模块导出
├── model_provider.py # ModelType枚举 + ModelProvider类（含预设工厂方法）
├── pipeline.py       # StreamingPipeline (LCEL链 + 前后处理器)
└── wrapper.py        # LLMWrapper简单封装（调用 PromptLoader）
```

## 核心类

### ModelProvider

提供可切换的模型源 + 预设工厂方法。

```python
class ModelType(Enum):
  OPENAI = "openai"
  ANTHROPIC = "anthropic"
  LOCAL_QWEN = "local_qwen"

class ModelProvider:
  def get_model(model_type, model_name) -> BaseChatModel

  # 预设工厂方法
  @classmethod
  def remote_large(cls) -> BaseChatModel   # GPT-4o
  @classmethod
  def remote_small(cls) -> BaseChatModel   # GPT-4o-mini
  @classmethod
  def local_large(cls) -> BaseChatModel    # Qwen2.5-7B-Instruct
  @classmethod
  def local_small(cls) -> BaseChatModel    # Qwen2.5-1.5B-Instruct
```

支持的模型源:
- OpenAI API (gpt-4o, gpt-4o-mini等)
- Anthropic API (claude-3等)
- 本地Qwen (通过vllm兼容OpenAI接口)

### StreamingPipeline

LangChain LCEL 管道封装。

```python
class StreamingPipeline:
  def __init__(model, system_prompt)
  def invoke(input_text, history) -> str
  async def ainvoke(input_text, history) -> str
```

### LLMWrapper

对外简单接口，组合 ModelProvider 和 StreamingPipeline。
通过 PromptLoader 获取系统提示词。

```python
class LLMWrapper:
  def __init__(model_type, model_name, persona)
  def chat(user_input, history) -> str
  async def achat(user_input, history) -> str
```

## 状态

- [x] ModelProvider 实现
- [x] 预设模型工厂方法 (remote_large/small, local_large/small)
- [x] StreamingPipeline 实现 (LCEL重构)
- [x] LLMWrapper 实现
