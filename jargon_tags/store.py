"""
短语与标签存储
支持精确匹配与向量检索
"""

import logging
from dataclasses import replace
from datetime import datetime
from typing import Optional

from memory.config import EmbeddingConfig
from memory.store import VectorStore

from .models import JargonEntry, PendingJargon, TagEntry

logger = logging.getLogger(__name__)


class JargonStore:
  """短语与标签数据存储"""

  def __init__(
    self,
    enable_vector_search: bool = True,
    persist_directory: Optional[str] = "data/jargon_store",
  ):
    self._known: dict[str, JargonEntry] = {}
    self._pending: dict[str, PendingJargon] = {}
    self._tags: dict[str, TagEntry] = {}
    self._phrase_index: dict[str, str] = {}

    self._vector_store: Optional[VectorStore] = None
    if enable_vector_search:
      try:
        cfg = EmbeddingConfig(
          model_name="BAAI/bge-small-zh-v1.5",
          persist_directory=persist_directory,
        )
        self._vector_store = VectorStore(
          collection_name="jargon_known",
          config=cfg,
        )
      except Exception as exc:
        logger.warning("向量存储初始化失败，降级为仅精确匹配: %s", exc)
        self._vector_store = None

  @property
  def vector_enabled(self) -> bool:
    """是否启用向量检索"""
    return self._vector_store is not None

  def list_known(self) -> list[JargonEntry]:
    """获取所有已知短语"""
    return list(self._known.values())

  def list_pending(self) -> list[PendingJargon]:
    """获取所有待解明短语"""
    return list(self._pending.values())

  def list_tags(self) -> list[TagEntry]:
    """获取所有标签"""
    return list(self._tags.values())

  def find_tag_by_name(self, name: str) -> Optional[TagEntry]:
    """按标签名查找标签条目"""
    return self._tags.get(name.strip())

  def find_known_by_phrase(self, phrase: str) -> Optional[JargonEntry]:
    """按短语原文查找已知条目"""
    entry_id = self._phrase_index.get(phrase.strip())
    if entry_id is None:
      return None
    return self._known.get(entry_id)

  def find_pending_by_phrase(self, phrase: str) -> Optional[PendingJargon]:
    """按短语原文查找待解明条目"""
    return self._pending.get(phrase.strip())

  def upsert_known(self, entry: JargonEntry) -> None:
    """写入或更新已知短语"""
    normalized = entry.phrase.strip()
    saved = replace(entry, phrase=normalized, updated_at=datetime.now())

    removed_ids: set[str] = set()
    existing_id = self._phrase_index.get(normalized)
    if existing_id is not None and existing_id != saved.entry_id:
      removed_ids.add(existing_id)
      self._known.pop(existing_id, None)

    current = self._known.get(saved.entry_id)
    if current is not None:
      current_phrase = current.phrase.strip()
      if current_phrase != normalized and self._phrase_index.get(current_phrase) == saved.entry_id:
        self._phrase_index.pop(current_phrase, None)

    self._known[saved.entry_id] = saved
    self._phrase_index[normalized] = saved.entry_id

    if self._vector_store is None:
      return

    try:
      delete_ids = {saved.entry_id, *removed_ids}
      self._vector_store.delete(list(delete_ids))
      doc = self._build_vector_doc(saved)
      metadata = {
        "entry_id": saved.entry_id,
        "phrase": saved.phrase,
        "tags": "|".join(saved.tags),
      }
      self._vector_store.add(saved.entry_id, doc, metadata)
    except Exception as exc:
      logger.warning("写入向量索引失败: %s", exc)

  def upsert_pending(self, pending: PendingJargon) -> None:
    """写入或更新待解明条目"""
    key = pending.phrase.strip()
    current = self._pending.get(key)

    if current is None:
      self._pending[key] = replace(
        pending,
        phrase=key,
        last_seen_at=datetime.now(),
      )
      return

    self._pending[key] = replace(
      current,
      candidate_brief=pending.candidate_brief or current.candidate_brief,
      candidate_tags=pending.candidate_tags or current.candidate_tags,
      notes=pending.notes or current.notes,
      seen_count=max(current.seen_count, pending.seen_count),
      asked_count=max(current.asked_count, pending.asked_count),
      status=pending.status or current.status,
      last_seen_at=datetime.now(),
    )

  def mark_pending_seen(self, phrase: str) -> None:
    """标记待解明条目再次出现"""
    key = phrase.strip()
    current = self._pending.get(key)
    if current is None:
      return
    self._pending[key] = replace(
      current,
      seen_count=current.seen_count + 1,
      last_seen_at=datetime.now(),
    )

  def mark_pending_asked(self, phrase: str) -> None:
    """标记待解明条目已被追问一次"""
    key = phrase.strip()
    current = self._pending.get(key)
    if current is None:
      return
    self._pending[key] = replace(
      current,
      asked_count=current.asked_count + 1,
      last_asked_at=datetime.now(),
    )

  def remove_pending(self, phrase: str) -> Optional[PendingJargon]:
    """删除待解明条目并返回原对象"""
    return self._pending.pop(phrase.strip(), None)

  def upsert_tag(self, entry: TagEntry) -> None:
    """写入或更新标签"""
    now = datetime.now()
    current = self._tags.get(entry.name)
    if current is None:
      self._tags[entry.name] = replace(entry, updated_at=now)
      return

    self._tags[entry.name] = replace(
      current,
      definition=entry.definition or current.definition,
      examples=entry.examples or current.examples,
      related_tags=entry.related_tags or current.related_tags,
      confidence=max(current.confidence, entry.confidence),
      updated_at=now,
    )

  def clear(self) -> None:
    """清空全部短语与标签数据"""
    self._known.clear()
    self._pending.clear()
    self._tags.clear()
    self._phrase_index.clear()

    if self._vector_store is not None:
      self._vector_store.clear()

  def search_exact(self, text: str) -> list[JargonEntry]:
    """在文本中执行逐字匹配"""
    text = text.strip()
    if not text:
      return []

    matched: list[JargonEntry] = []
    for phrase, entry_id in self._phrase_index.items():
      if phrase and phrase in text:
        entry = self._known.get(entry_id)
        if entry is not None:
          matched.append(entry)
    return matched

  def search_vector(
    self,
    query: str,
    top_k: int = 8,
  ) -> list[tuple[JargonEntry, float]]:
    """在已知短语中执行向量检索"""
    if self._vector_store is None:
      return []

    query = query.strip()
    if not query:
      return []

    try:
      docs = self._vector_store.search(query=query, top_k=top_k)
    except Exception as exc:
      logger.warning("向量检索失败: %s", exc)
      return []

    result: list[tuple[JargonEntry, float]] = []
    for doc, score in docs:
      entry_id = (doc.metadata or {}).get("entry_id")
      if not entry_id:
        continue
      entry = self._known.get(entry_id)
      if entry is None:
        continue
      result.append((entry, score))

    return result

  def decay_all_weights(self, coefficient_per_day: float, archive_threshold: float) -> None:
    """
    执行个体权重衰减，基于距上次衰减逝去的时间（以天计）。
    当 weight 降到 archive_threshold 以下时封存。
    """
    now = datetime.now()
    for entry_id, entry in list(self._known.items()):
      days_passed = (now - entry.last_decay_at).total_seconds() / 86400.0
      if days_passed > 0.01:
        decay_factor = coefficient_per_day ** days_passed
        new_weight = round(entry.weight * decay_factor, 4)
        new_status = entry.status
        if new_weight < archive_threshold and new_status == "known":
          new_status = "archived"
        saved = replace(
          entry, 
          weight=new_weight, 
          status=new_status,
          last_decay_at=now
        )
        self._known[entry_id] = saved

  @staticmethod
  def _build_vector_doc(entry: JargonEntry) -> str:
    """构建向量索引文档"""
    tags = "、".join(entry.tags) if entry.tags else "无"
    examples = " / ".join(entry.examples) if entry.examples else "无"
    return (
      f"短语: {entry.phrase}\n"
      f"简要含义: {entry.brief}\n"
      f"详细说明: {entry.details}\n"
      f"例句对照: {examples}\n"
      f"标签: {tags}"
    )
