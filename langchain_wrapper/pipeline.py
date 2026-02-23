"""
流式处理管道
使用 LCEL (LangChain Expression Language) 构建可扩展的处理管道
"""

from collections.abc import AsyncIterator
from typing import Callable, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough


# 类型别名：处理器函数签名
Processor = Callable[[str], str]


class StreamingPipeline:
  """
  流式处理管道
  使用 LCEL 构建，支持动态添加前处理器和后处理器
  """

  def __init__(
    self,
    model: BaseChatModel,
    system_prompt: str,
    max_history: int = 20
  ):
    """
    初始化管道

    Args:
      model: LangChain 模型实例
      system_prompt: 系统提示词
      max_history: 保留的最大历史消息数（对话轮数 * 2）
    """
    self.model = model
    self.system_prompt = system_prompt
    self.max_history = max_history

    # 可扩展的处理器列表
    self._preprocessors: list[Processor] = []
    self._postprocessors: list[Processor] = []

    # 构建提示模板
    self._prompt_template = ChatPromptTemplate.from_messages([
      ("system", "{system_prompt}"),
      MessagesPlaceholder(variable_name="history"),
      ("human", "{input}")
    ])

    # 输出解析器
    self._output_parser = StrOutputParser()

    # 重建管道
    self._rebuild_chain()

  def _rebuild_chain(self) -> None:
    """重建 LCEL 管道"""
    # 前处理链：依次应用所有前处理器到 input 字段
    def apply_preprocessors(data: dict) -> dict:
      input_text = data.get("input", "")
      for processor in self._preprocessors:
        input_text = processor(input_text)
      return {**data, "input": input_text}

    # 后处理链：依次应用所有后处理器到输出字符串
    def apply_postprocessors(output: str) -> str:
      for processor in self._postprocessors:
        output = processor(output)
      return output

    # 格式化历史记录
    def format_history(data: dict) -> dict:
      history = data.get("history")
      if history is None:
        formatted = []
      else:
        messages = []
        for user_msg, ai_msg in history:
          messages.append(HumanMessage(content=user_msg))
          messages.append(AIMessage(content=ai_msg))
        # 限制历史长度
        if len(messages) > self.max_history:
          messages = messages[-self.max_history:]
        formatted = messages
      return {**data, "history": formatted}

    # 注入系统提示词 + 动态上下文包裹 user input
    def inject_system_prompt(data: dict) -> dict:
      input_text = data.get("input", "")
      pre = data.get("pre_context", "")
      post = data.get("post_context", "")
      if pre:
        input_text = f"{pre}\n\n---\n\n{input_text}"
      if post:
        input_text = f"{input_text}\n\n---\n\n{post}"
      return {**data, "system_prompt": self.system_prompt, "input": input_text}

    # 基础管道（流式使用，不含后处理器）
    self._stream_chain = (
      RunnableLambda(inject_system_prompt)
      | RunnableLambda(format_history)
      | RunnableLambda(apply_preprocessors)
      | self._prompt_template
      | self.model
      | self._output_parser
    )

    # 完整管道（非流式使用，含后处理器）
    self._chain = self._stream_chain | RunnableLambda(apply_postprocessors)

  def add_preprocessor(
    self,
    processor: Processor,
    position: Optional[int] = None
  ) -> "StreamingPipeline":
    """
    添加前处理器

    Args:
      processor: 处理函数，接收字符串返回字符串
      position: 插入位置，None 表示追加到末尾

    Returns:
      self，支持链式调用
    """
    if position is None:
      self._preprocessors.append(processor)
    else:
      self._preprocessors.insert(position, processor)
    self._rebuild_chain()
    return self

  def add_postprocessor(
    self,
    processor: Processor,
    position: Optional[int] = None
  ) -> "StreamingPipeline":
    """
    添加后处理器

    Args:
      processor: 处理函数，接收字符串返回字符串
      position: 插入位置，None 表示追加到末尾

    Returns:
      self，支持链式调用
    """
    if position is None:
      self._postprocessors.append(processor)
    else:
      self._postprocessors.insert(position, processor)
    self._rebuild_chain()
    return self

  def remove_preprocessor(self, processor: Processor) -> bool:
    """
    移除前处理器

    Args:
      processor: 要移除的处理函数

    Returns:
      是否成功移除
    """
    try:
      self._preprocessors.remove(processor)
      self._rebuild_chain()
      return True
    except ValueError:
      return False

  def remove_postprocessor(self, processor: Processor) -> bool:
    """
    移除后处理器

    Args:
      processor: 要移除的处理函数

    Returns:
      是否成功移除
    """
    try:
      self._postprocessors.remove(processor)
      self._rebuild_chain()
      return True
    except ValueError:
      return False

  def clear_preprocessors(self) -> "StreamingPipeline":
    """清空所有前处理器"""
    self._preprocessors.clear()
    self._rebuild_chain()
    return self

  def clear_postprocessors(self) -> "StreamingPipeline":
    """清空所有后处理器"""
    self._postprocessors.clear()
    self._rebuild_chain()
    return self

  @property
  def preprocessors(self) -> list[Processor]:
    """获取前处理器列表（副本）"""
    return self._preprocessors.copy()

  @property
  def postprocessors(self) -> list[Processor]:
    """获取后处理器列表（副本）"""
    return self._postprocessors.copy()

  def invoke(
    self,
    input_text: str,
    history: Optional[list[tuple[str, str]]] = None,
    pre_context: str = "",
    post_context: str = "",
  ) -> str:
    """
    同步调用管道

    Args:
      input_text: 用户输入文本
      history: 对话历史
      pre_context: 前置上下文（如场景快照），放在 user input 之前
      post_context: 后置上下文（如记忆、话题），放在 user input 之后

    Returns:
      模型回复文本
    """
    return self._chain.invoke({
      "input": input_text,
      "history": history,
      "pre_context": pre_context,
      "post_context": post_context,
    })

  async def ainvoke(
    self,
    input_text: str,
    history: Optional[list[tuple[str, str]]] = None,
    pre_context: str = "",
    post_context: str = "",
  ) -> str:
    """
    异步调用管道

    Args:
      input_text: 用户输入文本
      history: 对话历史
      pre_context: 前置上下文（如场景快照），放在 user input 之前
      post_context: 后置上下文（如记忆、话题），放在 user input 之后

    Returns:
      模型回复文本
    """
    return await self._chain.ainvoke({
      "input": input_text,
      "history": history,
      "pre_context": pre_context,
      "post_context": post_context,
    })

  async def astream(
    self,
    input_text: str,
    history: Optional[list[tuple[str, str]]] = None,
    pre_context: str = "",
    post_context: str = "",
  ) -> AsyncIterator[str]:
    """
    异步流式调用管道，逐 token 返回

    注意：后处理器不会应用于流式输出，需在上层对完整文本做后处理。

    Args:
      input_text: 用户输入文本
      history: 对话历史
      pre_context: 前置上下文（如场景快照），放在 user input 之前
      post_context: 后置上下文（如记忆、话题），放在 user input 之后

    Yields:
      模型输出的文本片段（通常 1~几个字符）
    """
    async for chunk in self._stream_chain.astream({
      "input": input_text,
      "history": history,
      "pre_context": pre_context,
      "post_context": post_context,
    }):
      yield chunk


# ============================================================
# 内置处理器函数（可按需使用）
# ============================================================

def strip_whitespace(text: str) -> str:
  """去除首尾空白"""
  return text.strip()


def remove_empty_lines(text: str) -> str:
  """移除多余的空行"""
  lines = text.split("\n")
  result = []
  prev_empty = False
  for line in lines:
    is_empty = not line.strip()
    if is_empty and prev_empty:
      continue
    result.append(line)
    prev_empty = is_empty
  return "\n".join(result)


def limit_length(max_length: int) -> Processor:
  """
  创建长度限制处理器

  Args:
    max_length: 最大字符数

  Returns:
    处理器函数
  """
  def processor(text: str) -> str:
    if len(text) > max_length:
      return text[:max_length] + "..."
    return text
  return processor


def replace_text(old: str, new: str) -> Processor:
  """
  创建文本替换处理器

  Args:
    old: 要替换的文本
    new: 替换后的文本

  Returns:
    处理器函数
  """
  def processor(text: str) -> str:
    return text.replace(old, new)
  return processor


def add_prefix(prefix: str) -> Processor:
  """
  创建添加前缀处理器

  Args:
    prefix: 要添加的前缀

  Returns:
    处理器函数
  """
  def processor(text: str) -> str:
    return prefix + text
  return processor


def add_suffix(suffix: str) -> Processor:
  """
  创建添加后缀处理器

  Args:
    suffix: 要添加的后缀

  Returns:
    处理器函数
  """
  def processor(text: str) -> str:
    return text + suffix
  return processor
