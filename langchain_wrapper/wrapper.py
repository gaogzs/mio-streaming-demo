"""
LLM 包装器
提供简单的对外接口
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

from .model_provider import ModelType, ModelProvider
from .pipeline import StreamingPipeline

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from prompts import PromptLoader

if TYPE_CHECKING:
  from memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class LLMWrapper:
  """
  LLM 包装器
  组合 ModelProvider、PromptLoader 和 StreamingPipeline，提供简单的聊天接口
  """

  def __init__(
    self,
    model_type: ModelType = ModelType.OPENAI,
    model_name: Optional[str] = None,
    persona: str = "karin",
    max_history: int = 20,
    memory_manager: Optional["MemoryManager"] = None,
  ):
    """
    初始化 LLM 包装器

    Args:
      model_type: 模型类型
      model_name: 模型名称，不指定则使用默认值
      persona: 人设名称 (karin/sage/kuro)
      max_history: 保留的最大历史消息数
      memory_manager: 记忆管理器（可选，传入后启用记忆功能）
    """
    self.model_type = model_type
    self.model_name = model_name
    self.persona = persona
    self._memory = memory_manager

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

    # 最近一次使用的记忆上下文（供调试监控）
    self._last_extra_context: str = ""

    # 后台任务引用集合（防止被 GC 回收）
    self._background_tasks: set[asyncio.Task] = set()

  @property
  def has_memory(self) -> bool:
    """是否启用了记忆功能"""
    return self._memory is not None

  @property
  def memory_manager(self) -> Optional["MemoryManager"]:
    """获取记忆管理器实例"""
    return self._memory

  @property
  def last_extra_context(self) -> str:
    """最近一次使用的记忆上下文（供调试监控）"""
    return self._last_extra_context

  async def start_memory(self) -> None:
    """启动记忆系统定时任务（需在 asyncio 上下文中调用）"""
    if self._memory is not None:
      await self._memory.start()

  async def stop_memory(self) -> None:
    """停止记忆系统定时任务"""
    if self._memory is not None:
      await self._memory.stop()

  @property
  def history(self) -> list[tuple[str, str]]:
    """获取对话历史"""
    return self._history.copy()

  def clear_history(self) -> None:
    """清空对话历史"""
    self._history = []

  def _build_extra_context(
    self,
    user_input: str,
    rag_queries: Optional[list[str]] = None,
    topic_context: Optional[str] = None,
    scene_context: Optional[str] = None,
  ) -> str:
    """
    构建额外上下文（场景快照 + 记忆 + 话题）

    注入到 user message 前面（而非 system prompt），让模型
    明确区分"静态规则"和"当前动态状态"。

    Args:
      user_input: 用户输入（默认也用作 RAG 查询）
      rag_queries: 自定义 RAG 查询列表（如逐条弹幕），
        传入时用此列表代替 user_input 进行 RAG 检索
      topic_context: 话题上下文（来自话题管理器）
      scene_context: 场景快照（直播间状态概括）

    Returns:
      格式化的额外上下文文本
    """
    parts: list[str] = []

    if scene_context:
      parts.append(scene_context)

    if self._memory is not None:
      query: Union[str, list[str]] = rag_queries if rag_queries else user_input
      active_text, rag_text = self._memory.retrieve(query)
      parts.extend(p for p in [active_text, rag_text] if p)

    if topic_context:
      parts.append(topic_context)

    return "\n\n".join(parts)

  def chat(
    self,
    user_input: str,
    save_history: bool = True,
    rag_queries: Optional[list[str]] = None,
    topic_context: Optional[str] = None,
    scene_context: Optional[str] = None,
  ) -> str:
    """
    同步聊天

    Args:
      user_input: 用户输入
      save_history: 是否保存到历史记录
      rag_queries: 自定义 RAG 查询列表（逐条弹幕内容）
      topic_context: 话题上下文（来自话题管理器）
      scene_context: 场景快照（直播间状态概括）

    Returns:
      模型回复
    """
    extra_context = self._build_extra_context(
      user_input, rag_queries, topic_context, scene_context,
    )
    self._last_extra_context = extra_context
    response = self.pipeline.invoke(
      user_input, self._history, extra_context=extra_context,
    )

    if save_history:
      self._history.append((user_input, response))

    # 同步记录交互（不使用 LLM 总结）
    if self._memory is not None:
      self._memory.record_interaction_sync(user_input, response)

    return response

  async def achat(
    self,
    user_input: str,
    save_history: bool = True,
    rag_queries: Optional[list[str]] = None,
    topic_context: Optional[str] = None,
    scene_context: Optional[str] = None,
  ) -> str:
    """
    异步聊天

    Args:
      user_input: 用户输入
      save_history: 是否保存到历史记录
      rag_queries: 自定义 RAG 查询列表（逐条弹幕内容）
      topic_context: 话题上下文（来自话题管理器）
      scene_context: 场景快照（直播间状态概括）

    Returns:
      模型回复
    """
    extra_context = self._build_extra_context(
      user_input, rag_queries, topic_context, scene_context,
    )
    self._last_extra_context = extra_context
    response = await self.pipeline.ainvoke(
      user_input, self._history, extra_context=extra_context,
    )

    if save_history:
      self._history.append((user_input, response))

    # 异步记录交互（fire-and-forget，不阻塞返回）
    if self._memory is not None:
      task = asyncio.create_task(
        self._memory.record_interaction(user_input, response)
      )
      self._background_tasks.add(task)
      task.add_done_callback(self._background_tasks.discard)

    return response

  async def achat_stream(
    self,
    user_input: str,
    save_history: bool = True,
    rag_queries: Optional[list[str]] = None,
    topic_context: Optional[str] = None,
    scene_context: Optional[str] = None,
  ) -> AsyncIterator[str]:
    """
    异步流式聊天，逐 token yield

    流结束后自动执行后处理、保存历史、记录记忆。

    Args:
      user_input: 用户输入
      save_history: 是否保存到历史记录
      rag_queries: 自定义 RAG 查询列表（逐条弹幕内容）
      topic_context: 话题上下文（来自话题管理器）
      scene_context: 场景快照（直播间状态概括）

    Yields:
      模型输出的文本片段
    """
    extra_context = self._build_extra_context(
      user_input, rag_queries, topic_context, scene_context,
    )
    self._last_extra_context = extra_context
    full_response = ""
    completed = False

    try:
      async for chunk in self.pipeline.astream(
        user_input, self._history, extra_context=extra_context,
      ):
        full_response += chunk
        yield chunk
      completed = True
    finally:
      if completed:
        # 流式完成后：后处理 + 历史 + 记忆（与 achat 一致）
        for processor in self.pipeline.postprocessors:
          full_response = processor(full_response)

        if save_history:
          self._history.append((user_input, full_response))

        if self._memory is not None:
          task = asyncio.create_task(
            self._memory.record_interaction(user_input, full_response)
          )
          self._background_tasks.add(task)
          task.add_done_callback(self._background_tasks.discard)

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

  def debug_state(self) -> dict:
    """
    获取调试状态快照（供监控面板使用）

    Returns:
      包含当前运行状态的字典
    """
    return {
      "model_type": self.model_type.value,
      "model_name": self.model_name,
      "persona": self.persona,
      "history_length": len(self._history),
      "has_memory": self.has_memory,
      "background_tasks": len(self._background_tasks),
      "system_prompt_preview": self.pipeline.system_prompt[:200],
    }

  def memory_debug_state(self) -> Optional[dict]:
    """
    获取记忆系统的调试状态快照

    Returns:
      记忆系统状态字典，未启用记忆时返回 None
    """
    if self._memory is None:
      return None
    return self._memory.debug_state()

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
