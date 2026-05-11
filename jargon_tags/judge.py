"""
短语判官工具
提供规则候选提取与 LLM JSON 解析
"""

import json
import re
from typing import Any, Optional


_CANDIDATE_PATTERNS = [
  re.compile(r"[「\"“](.{2,12}?)[」\"”]"),
  re.compile(r"#(.{2,12}?)#"),
]


def extract_candidate_phrases(text: str) -> list[str]:
  """从文本中提取疑似短语候选"""
  text = text.strip()
  if not text:
    return []

  results: list[str] = []
  seen: set[str] = set()

  for pattern in _CANDIDATE_PATTERNS:
    for match in pattern.findall(text):
      candidate = match.strip()
      if not candidate:
        continue
      if len(candidate) > 12:
        continue
      if candidate in seen:
        continue
      seen.add(candidate)
      results.append(candidate)

  return results


def parse_json_response(text: str) -> Optional[dict[str, Any]]:
  """解析 LLM 返回的 JSON（容错 markdown 代码块与前后噪声）"""
  text = text.strip()
  if not text:
    return None

  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
  if text.endswith("```"):
    text = text.rsplit("```", 1)[0]
  text = text.strip()

  try:
    return json.loads(text)
  except json.JSONDecodeError:
    pass

  start = text.find("{")
  end = text.rfind("}")
  if start == -1 or end == -1 or end <= start:
    return None

  snippet = text[start : end + 1]
  try:
    return json.loads(snippet)
  except json.JSONDecodeError:
    return None


def normalize_discover_output(data: dict[str, Any]) -> dict[str, Any]:
  """标准化 discover_and_resolve 输出结构"""
  return {
    "new_candidates": data.get("new_candidates", []),
    "pending_resolutions": data.get("pending_resolutions", []),
    "known_revisions": data.get("known_revisions", []),
  }
