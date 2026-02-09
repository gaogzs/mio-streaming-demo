"""
记忆系统编排器
统一管理四层初始化、记忆读写、定时汇总和清理
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_huggingface import HuggingFaceEmbeddings

from .config import MemoryConfig
from .store import VectorStore
from .archive import MemoryArchive
from .layers.active import ActiveLayer
from .layers.temporary import TemporaryLayer
from .layers.summary import SummaryLayer
from .layers.static import StaticLayer
from .retriever import MemoryRetriever
from .prompts import INTERACTION_SUMMARY_PROMPT, PERIODIC_SUMMARY_PROMPT

logger = logging.getLogger(__name__)


class MemoryManager:
  """
  记忆系统顶层编排器

  职责：
  - 初始化四层记忆 + 共享 embeddings
  - 编排记忆读取（检索）和写入（交互记录）
  - 管理定时汇总和清理任务的生命周期
  """

  def __init__(
    self,
    persona: str,
    config: MemoryConfig = MemoryConfig(),
    summary_model: Optional[BaseChatModel] = None,
  ):
    """
    初始化记忆管理器

    Args:
      persona: 角色名称
      config: 记忆系统总配置
      summary_model: 用于总结的小 LLM（默认使用 ModelProvider.remote_small()）
    """
    # 创建共享 embeddings（避免重复加载模型）
    embeddings = HuggingFaceEmbeddings(
      model_name=config.embedding.model_name,
    )

    # 初始化归档器
    self._archive = MemoryArchive(persona)

    # 初始化四层
    self._temporary = TemporaryLayer(
      VectorStore("temporary", config.embedding, embeddings=embeddings),
      self._archive,
      config.temporary,
    )
    self._active = ActiveLayer(
      config=config.active,
      on_overflow=self._temporary.add,
    )
    self._summary_layer = SummaryLayer(
      VectorStore("summary", config.embedding, embeddings=embeddings),
      self._archive,
      config.summary,
    )
    self._static = StaticLayer(
      VectorStore("static", config.embedding, embeddings=embeddings),
      persona=persona,
    )
    self._static.load()

    # 跨层检索器
    self._retriever = MemoryRetriever(
      self._active,
      self._temporary,
      self._summary_layer,
      self._static,
      config=config.retrieval,
    )

    # 汇总用小 LLM
    self._summary_model = summary_model
    self._config = config

    # 定时任务句柄
    self._summary_task: Optional[asyncio.Task] = None
    self._cleanup_task: Optional[asyncio.Task] = None

    # 近期交互缓冲（供定时汇总使用）
    self._recent_interactions: list[tuple[str, str, datetime]] = []

  def _get_summary_model(self) -> BaseChatModel:
    """
    获取汇总用小 LLM（延迟初始化）

    Returns:
      BaseChatModel 实例
    """
    if self._summary_model is None:
      from langchain_wrapper.model_provider import ModelProvider
      self._summary_model = ModelProvider.remote_small()
    return self._summary_model

  def retrieve(self, query: str) -> tuple[str, str]:
    """
    执行跨层记忆检索

    Args:
      query: 查询文本（通常是用户最新输入）

    Returns:
      (active_text, rag_text) 元组
    """
    return self._retriever.retrieve(query)

  async def record_interaction(
    self,
    user_input: str,
    response: str,
  ) -> None:
    """
    异步记录一次交互

    使用小 LLM 将对话总结为第一人称记忆，写入 active 层，
    同时加入近期交互缓冲供定时汇总使用。

    Args:
      user_input: 用户输入
      response: LLM 回复
    """
    try:
      model = self._get_summary_model()
      prompt = INTERACTION_SUMMARY_PROMPT.format(
        input=user_input,
        response=response,
      )
      summary = await model.ainvoke(prompt)
      summary_text = summary.content if hasattr(summary, "content") else str(summary)
      summary_text = summary_text.strip()

      if summary_text:
        self._active.add(summary_text)
        self._recent_interactions.append(
          (user_input, response, datetime.now())
        )
        logger.debug("记录交互记忆: %s", summary_text)
    except Exception as e:
      logger.error("记录交互记忆失败: %s", e)

  def record_interaction_sync(
    self,
    user_input: str,
    response: str,
  ) -> None:
    """
    同步记录一次交互（不使用 LLM 总结，直接拼接原文）

    用于同步上下文中无法启动 asyncio task 的场景。

    Args:
      user_input: 用户输入
      response: LLM 回复
    """
    summary_text = f"我回复了一位观众：他说「{user_input}」，我说了「{response[:50]}」"
    self._active.add(summary_text)
    self._recent_interactions.append(
      (user_input, response, datetime.now())
    )

  async def start(self) -> None:
    """启动定时汇总和清理任务"""
    if self._summary_task is None:
      self._summary_task = asyncio.create_task(self._summary_loop())
      logger.info("记忆定时汇总任务已启动")

    if self._cleanup_task is None:
      self._cleanup_task = asyncio.create_task(self._cleanup_loop())
      logger.info("记忆定时清理任务已启动")

  async def stop(self) -> None:
    """停止定时任务"""
    for task, name in [
      (self._summary_task, "汇总"),
      (self._cleanup_task, "清理"),
    ]:
      if task is not None:
        task.cancel()
        try:
          await task
        except asyncio.CancelledError:
          pass
        logger.info("记忆定时%s任务已停止", name)

    self._summary_task = None
    self._cleanup_task = None

  async def _summary_loop(self) -> None:
    """
    定时汇总循环

    每 config.summary.interval_seconds 秒执行一次：
    1. 收集 active 层当前记忆 + 近期交互缓冲
    2. 用小 LLM 汇总为摘要
    3. 写入 summary 层
    4. 清空缓冲
    """
    interval = self._config.summary.interval_seconds
    while True:
      try:
        await asyncio.sleep(interval)
        await self._do_summary()
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error("定时汇总出错: %s", e)

  async def _do_summary(self) -> None:
    """执行一次汇总"""
    # 收集 active 层记忆
    active_memories = self._active.get_all()
    active_texts = [m.content for m in active_memories]

    # 收集近期交互
    recent = list(self._recent_interactions)

    # 如果没有任何内容可汇总，跳过
    if not active_texts and not recent:
      return

    active_str = "\n".join(f"- {t}" for t in active_texts) if active_texts else "（无）"
    recent_str = (
      "\n".join(
        f"- 观众说「{inp}」，我回复了「{resp[:50]}」"
        for inp, resp, _ in recent
      )
      if recent
      else "（无）"
    )

    prompt = PERIODIC_SUMMARY_PROMPT.format(
      active_memories=active_str,
      recent_interactions=recent_str,
    )

    try:
      model = self._get_summary_model()
      result = await model.ainvoke(prompt)
      summary_text = result.content if hasattr(result, "content") else str(result)
      summary_text = summary_text.strip()

      if summary_text:
        self._summary_layer.add(summary_text)
        self._recent_interactions.clear()
        logger.info("定时汇总完成: %s", summary_text[:60])
    except Exception as e:
      logger.error("定时汇总 LLM 调用失败: %s", e)

  async def _cleanup_loop(self) -> None:
    """
    定时清理循环

    每 config.summary.cleanup_interval_seconds 秒执行一次：
    调用 SummaryLayer.cleanup() 删除最低 significance 的记忆
    """
    interval = self._config.summary.cleanup_interval_seconds
    while True:
      try:
        await asyncio.sleep(interval)
        deleted = self._summary_layer.cleanup()
        if deleted > 0:
          logger.info("定时清理完成，删除了 %d 条低 significance 记忆", deleted)
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error("定时清理出错: %s", e)
