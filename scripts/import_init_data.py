"""
初始化黑话与标签数据导入脚本
将 generate_init_jargon.py 生成的 json 文件自动注入到向量库与内存库中
"""

import asyncio
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from streaming_studio.database import CommentDatabase
from jargon_tags import JargonTagsManager, JargonTagsConfig


async def main():
  out_dir = project_root / "data" / "init_jargon_data"
  tags_file = out_dir / "init_tags.json"
  jargons_file = out_dir / "init_jargons.json"

  if not tags_file.exists() and not jargons_file.exists():
    print("未找到需要导入的 JSON 文件，请先运行 generate_init_jargon.py")
    return

  print("正在初始化本地数据库与向量环境...")
  # 我们需要一个真实的 db 环境，这里由于只是写入黑话库，
  # CommentDatabase 只是透传，可以直接用基于文件的默认路径
  db = CommentDatabase(db_path=str(project_root / "data" / "studio_history.db"))
  
  # 初始化 manager
  config = JargonTagsConfig()
  manager = JargonTagsManager(persona="karin", database=db, config=config)

  if tags_file.exists():
    print(f"正在从 {tags_file} 导入标签...")
    count = manager.import_tags_from_json(str(tags_file))
    print(f"成功导入 {count} 个标签！")

  if jargons_file.exists():
    print(f"正在从 {jargons_file} 导入已知黑话（这可能会触发向量索引重新生成，稍等片刻）...")
    count = manager.import_known_jargons_from_json(str(jargons_file))
    print(f"成功导入 {count} 个黑话条目！")

  print("\n导入完成！由于 Chroma 会在写入后自动持久化，当前数据已立即可用。")


if __name__ == "__main__":
  asyncio.run(main())
