"""
流式处理管道
封装 LangChain 的消息模板和调用逻辑
"""

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


class StreamingPipeline:
  """
  流式处理管道
  封装系统提示词、对话历史和 LLM 调用
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

    # 构建提示模板
    self.prompt_template = ChatPromptTemplate.from_messages([
      ("system", "{system_prompt}"),
      MessagesPlaceholder(variable_name="history"),
      ("human", "{input}")
    ])

    # 构建链
    self.chain = self.prompt_template | self.model

  def _format_history(
    self,
    history: Optional[list[tuple[str, str]]] = None
  ) -> list:
    """
    格式化对话历史

    Args:
      history: 对话历史列表，每个元素是 (用户消息, AI回复) 元组

    Returns:
      LangChain 消息列表
    """
    if history is None:
      return []

    messages = []
    for user_msg, ai_msg in history:
      messages.append(HumanMessage(content=user_msg))
      messages.append(AIMessage(content=ai_msg))

    # 限制历史长度
    if len(messages) > self.max_history:
      messages = messages[-self.max_history:]

    return messages

  def _preprocess_input(self, input_text: str) -> str:
    """
    预处理输入文本

    Args:
      input_text: 原始输入

    Returns:
      处理后的输入
    """
    # 目前只做简单的空白清理
    return input_text.strip()

  def _postprocess_output(self, output: str) -> str:
    """
    后处理输出文本

    Args:
      output: 原始输出

    Returns:
      处理后的输出
    """
    # 清理可能的多余空白
    return output.strip()

  def invoke(
    self,
    input_text: str,
    history: Optional[list[tuple[str, str]]] = None
  ) -> str:
    """
    同步调用管道

    Args:
      input_text: 用户输入文本
      history: 对话历史

    Returns:
      模型回复文本
    """
    processed_input = self._preprocess_input(input_text)
    formatted_history = self._format_history(history)

    result = self.chain.invoke({
      "system_prompt": self.system_prompt,
      "history": formatted_history,
      "input": processed_input
    })

    return self._postprocess_output(result.content)

  async def ainvoke(
    self,
    input_text: str,
    history: Optional[list[tuple[str, str]]] = None
  ) -> str:
    """
    异步调用管道

    Args:
      input_text: 用户输入文本
      history: 对话历史

    Returns:
      模型回复文本
    """
    processed_input = self._preprocess_input(input_text)
    formatted_history = self._format_history(history)

    result = await self.chain.ainvoke({
      "system_prompt": self.system_prompt,
      "history": formatted_history,
      "input": processed_input
    })

    return self._postprocess_output(result.content)
