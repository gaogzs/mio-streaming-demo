"""
初始化短语与标签数据导入脚本
将 generate_init_jargon.py 生成的 json 文件自动注入到向量库与内存库中
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from jargon_tags import JargonEntry, JargonTagsManager, JargonTagsConfig, TagEntry
from streaming_studio.database import CommentDatabase


def _resolve_source_path(raw_path: str, source_dir: Path) -> Path:
  """
  解析导入源文件路径

  规则：
  - 绝对路径：直接使用
  - 仅文件名：在 source_dir 下查找
  - 其他相对路径（含目录）：按项目根目录解析
  """
  path = Path(raw_path)
  if path.is_absolute():
    return path
  if path.parent == Path("."):
    return source_dir / path.name
  return project_root / path


def _collect_json_files(source_path: Path) -> list[Path]:
  """收集目录下的 JSON 文件，或直接返回单个 JSON 文件。"""
  if source_path.is_file():
    return [source_path] if source_path.suffix.lower() == ".json" else []
  if not source_path.exists():
    return []
  return sorted(path for path in source_path.rglob("*.json") if path.is_file())


def _dedupe_paths(paths: list[Path]) -> list[Path]:
  """按绝对路径去重并保持首次出现顺序。"""
  seen: dict[str, Path] = {}
  for path in paths:
    key = str(path.resolve())
    if key not in seen:
      seen[key] = path
  return list(seen.values())


def _to_datetime(value: object):
  """将输入值转换为 datetime。"""
  from datetime import datetime

  if isinstance(value, str) and value.strip():
    try:
      return datetime.fromisoformat(value)
    except ValueError:
      pass
  return datetime.now()


def _to_float(value: object, default: float) -> float:
  """将输入值转换为 float。"""
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _to_int(value: object, default: int) -> int:
  """将输入值转换为 int。"""
  try:
    return int(value)
  except (TypeError, ValueError):
    return default


def _to_str_tuple(value: object) -> tuple[str, ...]:
  """将输入值转换为字符串元组。"""
  if isinstance(value, list):
    items = [str(item).strip() for item in value if str(item).strip()]
    return tuple(items)
  return tuple()


def _is_jargon_item(item: dict[str, object]) -> bool:
  """判断条目是否为短语条目。"""
  return bool(str(item.get("phrase", "")).strip()) and bool(str(item.get("brief", "")).strip()) and bool(str(item.get("details", "")).strip())


def _is_tag_item(item: dict[str, object]) -> bool:
  """判断条目是否为标签条目。"""
  return bool(str(item.get("name", "")).strip()) and bool(str(item.get("definition", "")).strip())


def _import_json_file(manager: JargonTagsManager, source_file: Path) -> tuple[int, int, int]:
  """从单个 JSON 文件中自动识别并导入短语与标签。"""
  raw = json.loads(source_file.read_text(encoding="utf-8"))
  if isinstance(raw, dict):
    items = [raw]
  elif isinstance(raw, list):
    items = raw
  else:
    print(f"跳过 {source_file}：顶层必须是数组或对象")
    return 0, 0, 1

  jargon_count = 0
  tag_count = 0
  skipped_count = 0

  for item in items:
    if not isinstance(item, dict):
      skipped_count += 1
      continue

    if _is_jargon_item(item):
      phrase = str(item.get("phrase", "")).strip()
      entry = JargonEntry(
        entry_id=str(item.get("entry_id", "")).strip() or f"manual_{phrase}",
        phrase=phrase,
        brief=str(item.get("brief", "")).strip(),
        details=str(item.get("details", "")).strip(),
        tags=_to_str_tuple(item.get("tags", [])),
        examples=_to_str_tuple(item.get("examples", [])),
        status=str(item.get("status", "known")),
        confidence=_to_float(item.get("confidence", 0.5), 0.5),
        weight=_to_float(item.get("weight", 1.0), 1.0),
        last_decay_at=_to_datetime(item.get("last_decay_at")),
        source_refs=_to_str_tuple(item.get("source_refs", [])),
        version=_to_int(item.get("version", 1), 1),
        created_at=_to_datetime(item.get("created_at")),
        updated_at=_to_datetime(item.get("updated_at")),
      )
      manager.upsert_jargon(entry)
      jargon_count += 1
      continue

    if _is_tag_item(item):
      entry = TagEntry(
        name=str(item.get("name", "")).strip(),
        definition=str(item.get("definition", "")).strip(),
        examples=_to_str_tuple(item.get("examples", [])),
        canonical_quotes=_to_str_tuple(item.get("canonical_quotes", [])),
        related_tags=_to_str_tuple(item.get("related_tags", [])),
        confidence=_to_float(item.get("confidence", 0.5), 0.5),
        created_at=_to_datetime(item.get("created_at")),
        updated_at=_to_datetime(item.get("updated_at")),
      )
      manager.upsert_tag(entry)
      tag_count += 1
      continue

    skipped_count += 1

  return jargon_count, tag_count, skipped_count


async def main():
  parser = argparse.ArgumentParser(description="初始化短语与标签数据")
  parser.add_argument(
    "--import-mode",
    choices=["append", "overwrite"],
    default="append",
    help="导入模式：append 追加到现有数据，overwrite 覆盖现有数据",
  )
  parser.add_argument(
    "--source-dir",
    default="data/init_jargon_data",
    help="源目录；会自动递归导入该目录下的所有 JSON 文件",
  )
  parser.add_argument(
    "--tags-file",
    default="mined_tags.json",
    help="额外的标签文件路径；会与 --source-dir 扫描结果合并后去重导入",
  )
  parser.add_argument(
    "--jargons-file",
    default="mined_jargons.json",
    help="额外的短语文件路径；会与 --source-dir 扫描结果合并后去重导入",
  )
  args = parser.parse_args()

  source_dir = Path(args.source_dir)
  if not source_dir.is_absolute():
    source_dir = project_root / source_dir
  tags_file = _resolve_source_path(args.tags_file, source_dir)
  jargons_file = _resolve_source_path(args.jargons_file, source_dir)

  source_files = _dedupe_paths(_collect_json_files(source_dir))
  explicit_files = [path for path in (tags_file, jargons_file) if path.exists()]
  import_files = _dedupe_paths(source_files + explicit_files)

  if not import_files:
    print("未找到需要导入的 JSON 文件，请检查 --source-dir / --tags-file / --jargons-file 参数")
    return

  print("正在初始化本地数据库与向量环境...")
  # 我们需要一个真实的 db 环境，这里由于只是写入短语库，
  # CommentDatabase 只是透传，可以直接用基于文件的默认路径
  db = CommentDatabase(db_path=str(project_root / "data" / "studio_history.db"))
  
  # 初始化 manager
  config = JargonTagsConfig()
  manager = JargonTagsManager(
    persona="karin",
    database=db,
    config=config,
    bootstrap_from_disk=(args.import_mode == "append"),
  )

  if args.import_mode == "overwrite":
    print("当前为覆盖式导入：将清空现有短语与标签数据后重新导入")
    manager.clear_all_data()

  total_jargons = 0
  total_tags = 0
  total_skipped = 0

  for source_file in import_files:
    print(f"正在处理 {source_file}...")
    jargon_count, tag_count, skipped_count = _import_json_file(manager, source_file)
    total_jargons += jargon_count
    total_tags += tag_count
    total_skipped += skipped_count
    print(f"  导入完成：短语 {jargon_count} 条，标签 {tag_count} 条，跳过 {skipped_count} 条")

  print(f"\n汇总：短语 {total_jargons} 条，标签 {total_tags} 条，跳过 {total_skipped} 条")

  persist_dir = project_root / "data" / "jargon_store"
  persist_known = persist_dir / "known_jargons.json"
  persist_tags = persist_dir / "tags.json"
  manager.export_known_jargons_to_json(str(persist_known))
  manager.export_tags_to_json(str(persist_tags))
  print(f"已写入持久化文件: {persist_known}")
  print(f"已写入持久化文件: {persist_tags}")

  print("\n导入完成！由于 Chroma 会在写入后自动持久化，当前数据已立即可用。")


if __name__ == "__main__":
  asyncio.run(main())
