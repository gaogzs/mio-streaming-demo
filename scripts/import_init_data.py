"""
初始化黑话与标签数据导入脚本
将 generate_init_jargon.py 生成的 json 文件自动注入到向量库与内存库中
"""

import asyncio
import argparse
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from jargon_tags import JargonTagsManager, JargonTagsConfig
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


async def main():
  parser = argparse.ArgumentParser(description="初始化黑话与标签数据")
  parser.add_argument(
    "--import-mode",
    choices=["append", "overwrite"],
    default="append",
    help="导入模式：append 追加到现有数据，overwrite 覆盖现有数据",
  )
  parser.add_argument(
    "--source-dir",
    default="data/init_jargon_data",
    help="默认源目录；当 --tags-file/--jargons-file 仅填文件名时在该目录查找",
  )
  parser.add_argument(
    "--tags-file",
    default="mined_tags.json",
    help="标签源文件路径；只填文件名时会在 --source-dir 下查找",
  )
  parser.add_argument(
    "--jargons-file",
    default="mined_jargons.json",
    help="黑话源文件路径；只填文件名时会在 --source-dir 下查找",
  )
  args = parser.parse_args()

  source_dir = Path(args.source_dir)
  if not source_dir.is_absolute():
    source_dir = project_root / source_dir
  tags_file = _resolve_source_path(args.tags_file, source_dir)
  jargons_file = _resolve_source_path(args.jargons_file, source_dir)

  if not tags_file.exists() and not jargons_file.exists():
    print("未找到需要导入的 JSON 文件，请检查 --tags-file / --jargons-file 参数")
    return

  print("正在初始化本地数据库与向量环境...")
  # 我们需要一个真实的 db 环境，这里由于只是写入黑话库，
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
    print("当前为覆盖式导入：将清空现有黑话与标签数据后重新导入")
    manager.clear_all_data()

  if tags_file.exists():
    print(f"正在从 {tags_file} 导入标签...")
    count = manager.import_tags_from_json(str(tags_file))
    print(f"成功导入 {count} 个标签！")

  if jargons_file.exists():
    print(f"正在从 {jargons_file} 导入已知黑话（这可能会触发向量索引重新生成，稍等片刻）...")
    count = manager.import_known_jargons_from_json(str(jargons_file))
    print(f"成功导入 {count} 个黑话条目！")

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
