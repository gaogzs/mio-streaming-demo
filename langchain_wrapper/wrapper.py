"""
LLM 包装器
提供简单的对外接口
"""

import sys
from pathlib import Path
from typing import Optional

from .model_provider import ModelType, ModelProvider
from .pipeline import StreamingPipeline

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from prompts import PromptLoader


class LLMWrapper:
  """
  LLM 包装器
  组合 ModelProvider、PromptLoader 和 StreamingPipeline，提供简单的聊天接口
  """

  def __init__(
    self,
    model_type: ModelType = ModelType.OPENAI,
    model_name: Optional[str] = None,
    persona: str = "mio",
    max_history: int = 20
  ):
    """
    初始化 LLM 包装器

    Args:
      model_type: 模型类型
      model_name: 模型名称，不指定则使用默认值
      persona: 人设名称 (mio/sage/kuro)
      max_history: 保留的最大历史消息数
    """
    self.model_type = model_type
    self.model_name = model_name
    self.persona = persona

    # 加载提示词
    prompt_loader = PromptLoader()
    system_prompt = prompt_loader.get_full_system_prompt(persona)

    # 创建模型
    provider = ModelProvider()
    model = provider.get_model(model_type, model_name)

    # 创建管道
    self.pipeline = StreamingPipeline(
      model=model,
      system_prompt=system_prompt,
      max_history=max_history
    )

    # 对话历史
    self._history: list[tuple[str, str]] = []

  @property
  def history(self) -> list[tuple[str, str]]:
    """获取对话历史"""
    return self._history.copy()

  def clear_history(self) -> None:
    """清空对话历史"""
    self._history = []

  def chat(self, user_input: str, save_history: bool = True) -> str:
    """
    同步聊天

    Args:
      user_input: 用户输入
      save_history: 是否保存到历史记录

    Returns:
      模型回复
    """
    response = self.pipeline.invoke(user_input, self._history)

    if save_history:
      self._history.append((user_input, response))

    return response

  async def achat(self, user_input: str, save_history: bool = True) -> str:
    """
    异步聊天

    Args:
      user_input: 用户输入
      save_history: 是否保存到历史记录

    Returns:
      模型回复
    """
    response = await self.pipeline.ainvoke(user_input, self._history)

    if save_history:
      self._history.append((user_input, response))

    return response

  def chat_with_context(
    self,
    user_input: str,
    context: str,
    save_history: bool = True
  ) -> str:
    """
    带上下文的同步聊天
    将上下文信息附加到用户输入中

    Args:
      user_input: 用户输入
      context: 上下文信息（如用户昵称等）
      save_history: 是否保存到历史记录

    Returns:
      模型回复
    """
    full_input = f"[{context}] {user_input}"
    return self.chat(full_input, save_history)

  async def achat_with_context(
    self,
    user_input: str,
    context: str,
    save_history: bool = True
  ) -> str:
    """
    带上下文的异步聊天

    Args:
      user_input: 用户输入
      context: 上下文信息
      save_history: 是否保存到历史记录

    Returns:
      模型回复
    """
    full_input = f"[{context}] {user_input}"
    return await self.achat(full_input, save_history)
