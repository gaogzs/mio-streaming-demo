"""
直播间核心模块
管理弹幕缓冲区和主播回复生成（双轨制：定时器 + 弹幕加速）
"""

import asyncio
import random
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
  管理弹幕缓冲区、调用 LLM 生成回复、分发回复给订阅者

  双轨制触发机制：
  - 定时器：每隔 min_interval~max_interval 秒随机触发一次
  - 弹幕加速：每条新弹幕缩短等待时间 1 秒
  """

  def __init__(
    self,
    llm_wrapper: Optional[LLMWrapper] = None,
    database: Optional[CommentDatabase] = None,
    recent_comments_limit: int = 20,
    min_interval: float = 1.0,
    max_interval: float = 10.0,
  ):
    """
    初始化直播间

    Args:
      llm_wrapper: LLM包装器，不指定则使用默认配置
      database: 数据库，不指定则使用默认配置
      recent_comments_limit: 每次触发时收集的最近弹幕数上限
      min_interval: 随机等待下限（秒）
      max_interval: 随机等待上限（秒）
    """
    self.llm_wrapper = llm_wrapper or LLMWrapper()
    self.database = database or CommentDatabase()
    self.recent_comments_limit = recent_comments_limit
    self.min_interval = min_interval
    self.max_interval = max_interval

    # 弹幕缓冲区（环形，保留足够历史）
    self._comment_buffer: deque[Comment] = deque(maxlen=200)

    # 新弹幕到达通知
    self._comment_arrived: asyncio.Event = asyncio.Event()
    self._pending_comment_count: int = 0

    # 上次回复时间（用于区分新旧弹幕）
    self._last_reply_time: Optional[datetime] = None

    # 最近一次发给模型的完整 prompt（供调试监控）
    self._last_prompt: Optional[str] = None

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
    发送弹幕到缓冲区

    Args:
      comment: 弹幕对象
    """
    self.database.save_comment(comment)
    self._comment_buffer.append(comment)
    self._pending_comment_count += 1
    self._comment_arrived.set()

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
          timeout=timeout,
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

    # 启动记忆定时任务
    await self.llm_wrapper.start_memory()

    self._main_task = asyncio.create_task(self._main_loop())

  async def stop(self) -> None:
    """停止直播间"""
    self._running = False

    # 停止记忆定时任务
    await self.llm_wrapper.stop_memory()

    if self._main_task:
      self._main_task.cancel()
      try:
        await self._main_task
      except asyncio.CancelledError:
        pass
      self._main_task = None

  async def _main_loop(self) -> None:
    """
    主循环：双轨定时器

    - 每轮生成 remaining = random(min_interval, max_interval) 秒的等待时间
    - 每收到一条新弹幕，remaining 减 1 秒（加速触发）
    - remaining 耗尽或自然超时后，收集弹幕并生成回复
    """
    while self._running:
      try:
        remaining = random.uniform(self.min_interval, self.max_interval)

        while remaining > 0:
          try:
            await asyncio.wait_for(
              self._comment_arrived.wait(),
              timeout=remaining,
            )
            # 有新弹幕到达，先读计数再清除事件
            count = self._pending_comment_count
            self._pending_comment_count = 0
            self._comment_arrived.clear()
            remaining = max(0.0, remaining - count)
          except asyncio.TimeoutError:
            # 自然超时
            break

        old_comments, new_comments = self._collect_comments()

        if not old_comments and not new_comments:
          continue

        response = await self._generate_response(old_comments, new_comments)

        if response:
          self.database.save_response(response)
          await self._response_queue.put(response)

          for callback in self._response_callbacks:
            try:
              callback(response)
            except Exception as e:
              print(f"回调执行错误: {e}")

          self._last_reply_time = datetime.now()

      except asyncio.CancelledError:
        break
      except Exception as e:
        print(f"主循环错误: {e}")
        await asyncio.sleep(1)

  def _collect_comments(self) -> tuple[list[Comment], list[Comment]]:
    """
    从缓冲区收集最近弹幕，按上次回复时间分割为旧弹幕和新弹幕

    Returns:
      (old_comments, new_comments) 元组
      - old_comments: 上次回复之前的弹幕（背景参考）
      - new_comments: 上次回复之后的新弹幕
    """
    recent = list(self._comment_buffer)[-self.recent_comments_limit:]

    if self._last_reply_time is None:
      return [], recent

    old = [c for c in recent if c.timestamp < self._last_reply_time]
    new = [c for c in recent if c.timestamp >= self._last_reply_time]
    return old, new

  @staticmethod
  def _format_comment(comment: Comment, now: datetime) -> str:
    """
    格式化单条弹幕

    格式: [14:23:05 / 35秒前] 花凛 (id: user_abc): 主播唱首歌

    Args:
      comment: 弹幕对象
      now: 当前时间（用于计算相对时间）

    Returns:
      格式化后的字符串
    """
    time_str = comment.timestamp.strftime("%H:%M:%S")
    delta = now - comment.timestamp
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
      relative = f"{total_seconds}秒前"
    elif total_seconds < 3600:
      minutes = total_seconds // 60
      seconds = total_seconds % 60
      relative = f"{minutes}分{seconds}秒前"
    else:
      hours = total_seconds // 3600
      minutes = (total_seconds % 3600) // 60
      relative = f"{hours}小时{minutes}分前"

    return f"[{time_str} / {relative}] {comment.nickname} (id: {comment.user_id}): {comment.content}"

  def _format_comments_for_prompt(
    self,
    old_comments: list[Comment],
    new_comments: list[Comment],
  ) -> str:
    """
    组合弹幕为 LLM 输入 prompt

    Args:
      old_comments: 上次回复前的弹幕
      new_comments: 上次回复后的新弹幕

    Returns:
      格式化后的 prompt 字符串
    """
    now = datetime.now()
    parts = []

    if old_comments:
      lines = [f"- {self._format_comment(c, now)}" for c in old_comments]
      parts.append("【上次回复前的弹幕（背景参考）】\n" + "\n".join(lines))

    if new_comments:
      lines = [f"- {self._format_comment(c, now)}" for c in new_comments]
      parts.append("【上次回复后的新弹幕】\n" + "\n".join(lines))
    else:
      # 计算距离最近一条弹幕的沉默时长
      silence_msg = "【上次回复后无人说话】"
      if old_comments:
        last_comment = old_comments[-1]
        silence_seconds = int((now - last_comment.timestamp).total_seconds())
        silence_msg += f"\n（已经 {silence_seconds} 秒没人说话了）"
      parts.append(silence_msg)

    return "\n\n".join(parts)

  async def _generate_response(
    self,
    old_comments: list[Comment],
    new_comments: list[Comment],
  ) -> Optional[StreamerResponse]:
    """
    根据弹幕生成回复

    Args:
      old_comments: 上次回复前的弹幕（背景参考）
      new_comments: 上次回复后的新弹幕

    Returns:
      回复对象
    """
    prompt = self._format_comments_for_prompt(old_comments, new_comments)
    self._last_prompt = prompt

    try:
      content = await self.llm_wrapper.achat(prompt)
    except Exception as e:
      print(f"LLM 调用错误: {e}")
      return None

    reply_ids = tuple(c.id for c in new_comments)
    return StreamerResponse(content=content, reply_to=reply_ids)

  def debug_state(self) -> dict:
    """
    获取调试状态快照（供监控面板使用）

    Returns:
      包含当前运行状态的字典
    """
    recent = list(self._comment_buffer)[-10:]
    return {
      "is_running": self._running,
      "min_interval": self.min_interval,
      "max_interval": self.max_interval,
      "buffer_size": len(self._comment_buffer),
      "buffer_max": self._comment_buffer.maxlen,
      "pending_comment_count": self._pending_comment_count,
      "last_reply_time": (
        self._last_reply_time.isoformat() if self._last_reply_time else None
      ),
      "last_prompt": self._last_prompt,
      "recent_comments": [
        {
          "nickname": c.nickname,
          "user_id": c.user_id,
          "content": c.content,
          "timestamp": c.timestamp.strftime("%H:%M:%S"),
        }
        for c in recent
      ],
      "total_comments": self.database.get_comment_count(),
      "total_responses": self.database.get_response_count(),
    }

  def get_stats(self) -> dict:
    """
    获取统计信息

    Returns:
      包含统计数据的字典
    """
    return {
      "is_running": self._running,
      "pending_comments": len(self._comment_buffer),
      "pending_responses": self._response_queue.qsize(),
      "total_comments": self.database.get_comment_count(),
      "total_responses": self.database.get_response_count(),
      "callback_count": len(self._response_callbacks),
    }
