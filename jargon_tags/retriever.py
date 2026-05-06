"""
黑话检索器
组合逐字匹配与向量检索，并执行标签过滤
"""

from collections import defaultdict

from .models import JargonEntry
from .store import JargonStore


class JargonRetriever:
  """黑话检索器"""

  def __init__(
    self,
    store: JargonStore,
    exact_match_boost: float = 1.8,
    vector_match_boost: float = 1.0,
    tag_match_boost: float = 1.2,
  ):
    self._store = store
    self._exact_match_boost = exact_match_boost
    self._vector_match_boost = vector_match_boost
    self._tag_match_boost = tag_match_boost

  def retrieve_for_texts(
    self,
    texts: list[str],
    active_tags: tuple[str, ...],
    top_k: int,
  ) -> list[JargonEntry]:
    """按输入文本批量召回黑话"""
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
    filtered: list[tuple[JargonEntry, float]] = []
    fallback: list[tuple[JargonEntry, float]] = []

    for entry_id, base_score in score_map.items():
      entry = entry_map[entry_id]
      
      if entry.status == "archived":
        continue
      
      entry_tags = set(entry.tags)
      score = base_score * entry.weight

      if not entry_tags:
        fallback.append((entry, score))
        continue

      if active.intersection(entry_tags):
        score *= self._tag_match_boost
        filtered.append((entry, score))
      elif "普通网民" in entry_tags:
        fallback.append((entry, score))

    ranked = sorted(filtered, key=lambda item: item[1], reverse=True)
    if not ranked:
      ranked = sorted(fallback, key=lambda item: item[1], reverse=True)

    return [entry for entry, _ in ranked[:top_k]]
