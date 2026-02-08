"""
直播间核心模块
管理弹幕队列和主播回复生成
"""

import asyncio
import sys
from pathlib import Path
from typing import Callable, Optional
from collections import deque

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from langchain_wrapper import LLMWrapper, ModelType
from .models import Comment, StreamerResponse
from .database import CommentDatabase


class StreamingStudio:
  """
  虚拟直播间核心类
  管理弹幕队列、调用 LLM 生成回复、分发回复给订阅者
  """

  def __init__(
    self,
    llm_wrapper: Optional[LLMWrapper] = None,
    database: Optional[CommentDatabase] = None,
    batch_size: int = 3,
    batch_wait_seconds: float = 2.0
  ):
    """
    初始化直播间

    Args:
      llm_wrapper: LLM包装器，不指定则使用默认配置
      database: 数据库，不指定则使用默认配置
      batch_size: 批量处理的最大弹幕数
      batch_wait_seconds: 等待弹幕的最长时间（秒）
    """
    self.llm_wrapper = llm_wrapper or LLMWrapper()
    self.database = database or CommentDatabase()
    self.batch_size = batch_size
    self.batch_wait_seconds = batch_wait_seconds

    # 弹幕队列
    self._comment_queue: asyncio.Queue[Comment] = asyncio.Queue()

    # 回复队列（供外部获取）
    self._response_queue: asyncio.Queue[StreamerResponse] = asyncio.Queue()

    # 回复回调函数列表
    self._response_callbacks: list[Callable[[StreamerResponse], None]] = []

    # 运行状态
    self._running = False
    self._main_task: Optional[asyncio.Task] = None

  @property
  def is_running(self) -> bool:
    """是否正在运行"""
    return self._running

  def send_comment(self, comment: Comment) -> None:
    """
    发送弹幕到队列

    Args:
      comment: 弹幕对象
    """
    # 保存到数据库
    self.database.save_comment(comment)
    # 放入队列
    self._comment_queue.put_nowait(comment)

  async def get_response(self, timeout: Optional[float] = None) -> Optional[StreamerResponse]:
    """
    获取主播回复

    Args:
      timeout: 超时时间（秒），None表示永久等待

    Returns:
      回复对象，超时返回None
    """
    try:
      if timeout is None:
        return await self._response_queue.get()
      else:
        return await asyncio.wait_for(
          self._response_queue.get(),
          timeout=timeout
        )
    except asyncio.TimeoutError:
      return None

  def on_response(self, callback: Callable[[StreamerResponse], None]) -> None:
    """
    注册回复回调函数

    Args:
      callback: 回调函数，接收 StreamerResponse 参数
    """
    self._response_callbacks.append(callback)

  def remove_callback(self, callback: Callable[[StreamerResponse], None]) -> None:
    """
    移除回复回调函数

    Args:
      callback: 要移除的回调函数
    """
    if callback in self._response_callbacks:
      self._response_callbacks.remove(callback)

  async def start(self) -> None:
    """启动直播间主循环"""
    if self._running:
      return

    self._running = True
    self._main_task = asyncio.create_task(self._main_loop())

  async def stop(self) -> None:
    """停止直播间"""
    self._running = False
    if self._main_task:
      self._main_task.cancel()
      try:
        await self._main_task
      except asyncio.CancelledError:
        pass
      self._main_task = None

  async def _main_loop(self) -> None:
    """主循环：收集弹幕并生成回复"""
    while self._running:
      try:
        # 收集一批弹幕
        comments = await self._collect_comments()

        if not comments:
          continue

        # 生成回复
        response = await self._generate_response(comments)

        if response:
          # 保存到数据库
          self.database.save_response(response)

          # 放入回复队列
          await self._response_queue.put(response)

          # 调用回调
          for callback in self._response_callbacks:
            try:
              callback(response)
            except Exception as e:
              print(f"回调执行错误: {e}")

      except asyncio.CancelledError:
        break
      except Exception as e:
        print(f"主循环错误: {e}")
        await asyncio.sleep(1)

  async def _collect_comments(self) -> list[Comment]:
    """
    收集一批弹幕

    Returns:
      弹幕列表
    """
    comments = []

    try:
      # 等待第一条弹幕
      first_comment = await asyncio.wait_for(
        self._comment_queue.get(),
        timeout=self.batch_wait_seconds
      )
      comments.append(first_comment)
    except asyncio.TimeoutError:
      return []

    # 尝试收集更多弹幕（非阻塞）
    deadline = asyncio.get_event_loop().time() + self.batch_wait_seconds

    while len(comments) < self.batch_size:
      remaining_time = deadline - asyncio.get_event_loop().time()
      if remaining_time <= 0:
        break

      try:
        comment = await asyncio.wait_for(
          self._comment_queue.get(),
          timeout=min(0.5, remaining_time)
        )
        comments.append(comment)
      except asyncio.TimeoutError:
        break

    return comments

  async def _generate_response(
    self,
    comments: list[Comment]
  ) -> Optional[StreamerResponse]:
    """
    根据弹幕生成回复

    Args:
      comments: 弹幕列表

    Returns:
      回复对象
    """
    if not comments:
      return None

    # 组合弹幕内容
    combined_input = "\n".join(c.format_for_llm() for c in comments)

    # 调用 LLM
    try:
      content = await self.llm_wrapper.achat(combined_input)
    except Exception as e:
      print(f"LLM 调用错误: {e}")
      return None

    # 创建回复
    return StreamerResponse(
      content=content,
      reply_to=tuple(c.id for c in comments)
    )

  def get_stats(self) -> dict:
    """
    获取统计信息

    Returns:
      包含统计数据的字典
    """
    return {
      "is_running": self._running,
      "pending_comments": self._comment_queue.qsize(),
      "pending_responses": self._response_queue.qsize(),
      "total_comments": self.database.get_comment_count(),
      "total_responses": self.database.get_response_count(),
      "callback_count": len(self._response_callbacks)
    }
