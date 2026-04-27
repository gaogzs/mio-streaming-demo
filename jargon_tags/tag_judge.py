"""
标签判官工具
"""

from typing import Any


def normalize_tag_output(data: dict[str, Any]) -> dict[str, Any]:
  """标准化标签判官输出结构"""
  return {
    "tag_updates": data.get("tag_updates", []),
    "active_tag_suggestions": data.get("active_tag_suggestions", []),
    "indirect_question_suggestions": data.get("indirect_question_suggestions", []),
  }
