"""
跨层记忆检索器
支持两种检索模式：per-layer quota / weighted merge
"""

from typing import Optional

from langchain_core.runnables import RunnableLambda

from .config import RetrievalConfig
from .formatter import format_active_memories, format_retrieved_memories
from .layers.base import MemoryEntry
from .layers.active import ActiveLayer
from .layers.temporary import TemporaryLayer
from .layers.summary import SummaryLayer
from .layers.static import StaticLayer


class MemoryRetriever:
  """
  跨层记忆检索器

  协调 active / temporary / summary / static 四层的检索，
  按配置模式合并结果，统一排序后输出。

  支持两种模式（通过 config.retrieval.mode 切换）：
  - "quota": 每层分配固定取回数量
  - "weighted": 所有 RAG 层合并取回，按层级系数加权后重排
  """

  def __init__(
    self,
    active: ActiveLayer,
    temporary: TemporaryLayer,
    summary: SummaryLayer,
    static: StaticLayer,
    config: Optional[RetrievalConfig] = None,
  ):
    """
    初始化检索器

    Args:
      active: active 层实例
      temporary: temporary 层实例
      summary: summary 层实例
      static: static 层实例
      config: 检索配置
    """
    self._active = active
    self._temporary = temporary
    self._summary = summary
    self._static = static
    self._config = config or RetrievalConfig()
    self.session_id: Optional[str] = None

  def retrieve(self, query: str) -> tuple[str, str]:
    """
    执行跨层检索

    Args:
      query: 查询文本（通常是用户最新输入）

    Returns:
      (active_text, rag_text) 元组：
        active_text: active 层格式化文本（时序直接注入）
        rag_text: RAG 层格式化文本（temporary + summary + static）
    """
    # active 层：全量直接取出
    active_memories = self._active.get_all()
    active_entries = [
      MemoryEntry(
        id=m.id,
        content=m.content,
        layer="active",
        timestamp=m.timestamp,
      )
      for m in active_memories
    ]
    active_text = format_active_memories(active_entries)

    # RAG 层检索
    if self._config.mode == "weighted":
      rag_entries = self._retrieve_weighted(query)
    else:
      rag_entries = self._retrieve_quota(query)

    rag_text = format_retrieved_memories(
      rag_entries,
      current_session_id=self.session_id,
    )

    return active_text, rag_text

  def _retrieve_quota(self, query: str) -> list[MemoryEntry]:
    """per-layer quota 模式：每层独立检索固定数量"""
    entries = []

    if self._config.quota_temporary > 0:
      entries.extend(
        self._temporary.retrieve(query, top_k=self._config.quota_temporary)
      )

    if self._config.quota_summary > 0:
      entries.extend(
        self._summary.retrieve(query, top_k=self._config.quota_summary)
      )

    if self._config.quota_static > 0:
      entries.extend(
        self._static.retrieve(query, top_k=self._config.quota_static)
      )

    return entries

  def _retrieve_weighted(self, query: str) -> list[MemoryEntry]:
    """
    weighted 模式：所有层合并取回，按层级系数加权后重排

    多取回 overfetch_multiplier 倍的结果，加权后取 top-k。
    """
    total_quota = (
      self._config.quota_temporary
      + self._config.quota_summary
      + self._config.quota_static
    )
    overfetch = total_quota * self._config.weighted_overfetch_multiplier

    # 每层多取回
    per_layer = max(1, overfetch // 3)
    all_entries = []

    all_entries.extend(
      self._temporary.retrieve(query, top_k=per_layer)
    )
    all_entries.extend(
      self._summary.retrieve(query, top_k=per_layer)
    )
    all_entries.extend(
      self._static.retrieve(query, top_k=per_layer)
    )

    # 加权打分
    weight_map = {
      "temporary": self._config.weight_temporary,
      "summary": self._config.weight_summary,
      "static": self._config.weight_static,
    }

    weighted = []
    for entry in all_entries:
      w = weight_map.get(entry.layer, 1.0)
      # Chroma 返回的 score 越小越相似，加权时取倒数使大的更好
      # 这里简单地用 weight / (1 + score) 作为加权分
      weighted_score = w / (1.0 + entry.score)
      weighted.append((entry, weighted_score))

    # 按加权分降序排列，取 top-k
    weighted.sort(key=lambda x: x[1], reverse=True)
    return [entry for entry, _ in weighted[:total_quota]]

  def as_runnable(self) -> RunnableLambda:
    """
    获取 LCEL 兼容的 Runnable

    输入: dict（须含 "input" 键）
    输出: dict，原始数据 + "active_memories" + "retrieved_memories"

    Returns:
      RunnableLambda
    """
    def _invoke(data: dict) -> dict:
      query = data.get("input", "")
      if not query:
        return {**data, "active_memories": "", "retrieved_memories": ""}

      active_text, rag_text = self.retrieve(query)
      return {
        **data,
        "active_memories": active_text,
        "retrieved_memories": rag_text,
      }

    return RunnableLambda(_invoke)
