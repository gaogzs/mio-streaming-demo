"""
LCEL 兼容的记忆检索器
封装 MemoryStore，提供 RunnableLambda 以便集成到 LangChain 管道
"""

from typing import Optional

from langchain_core.runnables import RunnableLambda

from .category import MemoryCategory
from .formatter import format_memories
from .store import MemoryStore


class MemoryRetriever:
  """
  记忆检索器 — LCEL 包装器

  将 MemoryStore 的检索能力封装为 RunnableLambda，
  可直接插入 LCEL 管道中使用。

  Runnable 行为：
    输入: dict，必须含 "input" 键（用户输入文本）
    输出: dict，原始数据 + "memories" 键（格式化后的记忆文本）

  使用示例（未来集成）：
    retriever = MemoryRetriever(store, top_k=3)
    chain = (
      RunnableLambda(inject_system_prompt)
      | retriever.as_runnable()
      | RunnableLambda(format_history)
      | prompt_template
      | model
      | output_parser
    )
  """

  def __init__(
    self,
    store: MemoryStore,
    top_k: int = 5,
    category_filter: Optional[MemoryCategory] = None,
  ):
    """
    初始化检索器

    Args:
      store: MemoryStore 实例
      top_k: 每次检索返回的最大记忆数
      category_filter: 固定的类别过滤（可选）
    """
    self._store = store
    self._top_k = top_k
    self._category_filter = category_filter

  def _retrieve_and_inject(self, data: dict) -> dict:
    """
    检索相关记忆并注入到数据字典中

    Args:
      data: 管道数据，须含 "input" 键

    Returns:
      新字典，包含原始数据 + "memories" 键
    """
    query = data.get("input", "")

    if not query:
      return {**data, "memories": ""}

    results = self._store.retrieve(
      query=query,
      top_k=self._top_k,
      category_filter=self._category_filter,
    )

    formatted = format_memories(results)
    return {**data, "memories": formatted}

  def as_runnable(self) -> RunnableLambda:
    """
    获取 LCEL 兼容的 Runnable

    Returns:
      RunnableLambda，可直接用于 LCEL 管道的 | 运算符
    """
    return RunnableLambda(self._retrieve_and_inject)
