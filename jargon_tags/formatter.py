"""
黑话与标签 prompt 格式化
"""

import random

from .models import JargonEntry, PendingJargon


def pick_pending_questions(
  pending_items: list[PendingJargon],
  max_count: int,
  pick_mode: str,
) -> list[PendingJargon]:
  """挑选本轮追问的待解明黑话"""
  if max_count <= 0 or not pending_items:
    return []

  # 优先追问近期出现且追问次数少的条目
  sorted_items = sorted(
    pending_items,
    key=lambda x: (x.asked_count, -x.seen_count, x.last_seen_at),
  )

  candidates = sorted_items[: max(max_count * 2, max_count)]
  if pick_mode == "random_k" and len(candidates) > max_count:
    return random.sample(candidates, k=max_count)

  return candidates[:max_count]


def format_reference_context(
  entries: list[JargonEntry],
  active_tags: tuple[str, ...],
  pending_to_ask: list[PendingJargon],
  indirect_hints: tuple[str, ...] = tuple(),
) -> str:
  """格式化参考模式 prompt 片段"""
  if not entries and not pending_to_ask:
    return ""

  lines = ["【黑话与风格参考】"]

  tags_text = "、".join(active_tags) if active_tags else "无"
  lines.append(f"- 当前活跃标签: {tags_text}")

  if entries:
    lines.append("- 可参考黑话:")
    for entry in entries:
      tag_text = "、".join(entry.tags) if entry.tags else "普通网民"
      lines.append(f"  - {entry.phrase}: {entry.brief}（标签: {tag_text}）")

  if pending_to_ask:
    lines.append("- 待解明词（可自然追问其含义，别一次问太多）:")
    for item in pending_to_ask:
      lines.append(f"  - {item.phrase}")

  if indirect_hints:
    lines.append("- 群体标签可间接提问提示（按人设酌情使用）:")
    for hint in indirect_hints:
      lines.append(f"  - {hint}")

  return "\n".join(lines)
