"""
短语检索器
组合逐字匹配与向量检索，并使用标签作为加权信号
"""

from collections import defaultdict

from .models import JargonEntry
from .store import JargonStore


class JargonRetriever:
  """短语检索器"""

  def __init__(
    self,
    store: JargonStore,
    exact_match_boost: float = 1.8,
    vector_match_boost: float = 1.0,
    tag_match_boost: float = 1.2,
    indirect_tag_match_boost: float = 1.05,
    tag_mismatch_penalty: float = 0.92,
    retrieval_min_score: float = 0.12,
  ):
    self._store = store
    self._exact_match_boost = exact_match_boost
    self._vector_match_boost = vector_match_boost
    self._tag_match_boost = tag_match_boost
    self._indirect_tag_match_boost = indirect_tag_match_boost
    self._tag_mismatch_penalty = tag_mismatch_penalty
    self._retrieval_min_score = retrieval_min_score

  def retrieve_for_texts(
    self,
    texts: list[str],
    active_tags: tuple[str, ...],
    top_k: int,
  ) -> list[JargonEntry]:
    """按输入文本批量召回短语"""
    if not texts:
      return []

    score_map: dict[str, float] = defaultdict(float)
    entry_map: dict[str, JargonEntry] = {}

    for text in texts:
      text = text.strip()
      if not text:
        continue

      exact_hits = self._store.search_exact(text)
      for entry in exact_hits:
        entry_map[entry.entry_id] = entry
        score_map[entry.entry_id] += self._exact_match_boost

      vector_hits = self._store.search_vector(text, top_k=top_k)
      for entry, raw_score in vector_hits:
        entry_map[entry.entry_id] = entry
        similarity = 1.0 / (1.0 + max(raw_score, 0.0))
        score_map[entry.entry_id] += similarity * self._vector_match_boost

    if not score_map:
      return []

    active = set(active_tags)
    indirect_tags = set()
    for tag_name in active_tags:
      tag_obj = self._store.find_tag_by_name(tag_name)
      if tag_obj and tag_obj.related_tags:
        indirect_tags.update(tag_obj.related_tags)

    ranked: list[tuple[JargonEntry, float]] = []

    for entry_id, base_score in score_map.items():
      entry = entry_map[entry_id]

      if entry.status == "archived":
        continue

      entry_tags = set(entry.tags)
      score = base_score * entry.weight

      if active.intersection(entry_tags):
        score *= self._tag_match_boost
      elif indirect_tags.intersection(entry_tags):
        score *= self._indirect_tag_match_boost
      elif entry_tags:
        score *= self._tag_mismatch_penalty

      if score >= self._retrieval_min_score:
        ranked.append((entry, score))

    ranked.sort(key=lambda item: item[1], reverse=True)

    return [entry for entry, _ in ranked[:top_k]]
