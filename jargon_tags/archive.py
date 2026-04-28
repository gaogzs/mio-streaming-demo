"""
黑话与标签 JSON 导入导出
"""

import json
from datetime import datetime
from pathlib import Path

from .models import JargonEntry, TagEntry


def export_known_jargons(path: str, entries: list[JargonEntry]) -> None:
  """导出已知黑话为 JSON"""
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  payload = [
    {
      "entry_id": e.entry_id,
      "phrase": e.phrase,
      "brief": e.brief,
      "details": e.details,
      "tags": list(e.tags),
      "examples": list(e.examples),
      "status": e.status,
      "confidence": e.confidence,
      "source_refs": list(e.source_refs),
      "version": e.version,
      "created_at": e.created_at.isoformat(),
      "updated_at": e.updated_at.isoformat(),
    }
    for e in entries
  ]
  target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_tags(path: str, entries: list[TagEntry]) -> None:
  """导出标签为 JSON"""
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  payload = [
    {
      "name": e.name,
      "definition": e.definition,
      "examples": list(e.examples),
      "related_tags": list(e.related_tags),
      "confidence": e.confidence,
      "created_at": e.created_at.isoformat(),
      "updated_at": e.updated_at.isoformat(),
    }
    for e in entries
  ]
  target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_known_jargons(path: str) -> list[JargonEntry]:
  """从 JSON 导入已知黑话"""
  source = Path(path)
  if not source.exists():
    raise FileNotFoundError(f"黑话文件不存在: {source}")

  raw = json.loads(source.read_text(encoding="utf-8"))
  if not isinstance(raw, list):
    raise ValueError("黑话导入文件格式错误：顶层必须是数组")

  result: list[JargonEntry] = []
  for item in raw:
    if not isinstance(item, dict):
      continue
    phrase = str(item.get("phrase", "")).strip()
    brief = str(item.get("brief", "")).strip()
    details = str(item.get("details", "")).strip()
    if not phrase or not brief or not details:
      continue

    result.append(
      JargonEntry(
        entry_id=str(item.get("entry_id", "")).strip() or f"manual_{phrase}",
        phrase=phrase,
        brief=brief,
        details=details,
        tags=_to_str_tuple(item.get("tags", [])),
        examples=_to_str_tuple(item.get("examples", [])),
        status=str(item.get("status", "known")),
        confidence=_to_float(item.get("confidence", 0.5), 0.5),
        source_refs=_to_str_tuple(item.get("source_refs", [])),
        version=_to_int(item.get("version", 1), 1),
        created_at=_to_datetime(item.get("created_at")),
        updated_at=_to_datetime(item.get("updated_at")),
      )
    )

  return result


def import_tags(path: str) -> list[TagEntry]:
  """从 JSON 导入标签"""
  source = Path(path)
  if not source.exists():
    raise FileNotFoundError(f"标签文件不存在: {source}")

  raw = json.loads(source.read_text(encoding="utf-8"))
  if not isinstance(raw, list):
    raise ValueError("标签导入文件格式错误：顶层必须是数组")

  result: list[TagEntry] = []
  for item in raw:
    if not isinstance(item, dict):
      continue
    name = str(item.get("name", "")).strip()
    definition = str(item.get("definition", "")).strip()
    if not name or not definition:
      continue

    result.append(
      TagEntry(
        name=name,
        definition=definition,
        examples=_to_str_tuple(item.get("examples", [])),
        related_tags=_to_str_tuple(item.get("related_tags", [])),
        confidence=_to_float(item.get("confidence", 0.5), 0.5),
        created_at=_to_datetime(item.get("created_at")),
        updated_at=_to_datetime(item.get("updated_at")),
      )
    )

  return result


def _to_datetime(value: object) -> datetime:
  """将输入值转换为 datetime，失败时返回当前时间"""
  if isinstance(value, str) and value.strip():
    try:
      return datetime.fromisoformat(value)
    except ValueError:
      pass
  return datetime.now()


def _to_str_tuple(value: object) -> tuple[str, ...]:
  """将输入值转换为字符串元组"""
  if isinstance(value, list):
    items = [str(x).strip() for x in value if str(x).strip()]
    return tuple(items)
  return tuple()


def _to_float(value: object, default: float) -> float:
  """将输入值转换为 float"""
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _to_int(value: object, default: int) -> int:
  """将输入值转换为 int"""
  try:
    return int(value)
  except (TypeError, ValueError):
    return default
