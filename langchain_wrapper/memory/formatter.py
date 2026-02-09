"""
记忆格式化工具
将检索到的记忆文档格式化为可嵌入 prompt 的文本段落
"""

from langchain_core.documents import Document

from .category import MemoryCategory


def format_memories(results: list[tuple[Document, float]]) -> str:
  """
  将检索结果格式化为完整格式（含类别标签 + 时间戳）

  格式示例：
    【相关记忆】
    - [用户偏好] 用户喜欢打篮球 (2026-02-08 14:23)
    - [话题] 曾讨论过NBA总决赛 (2026-02-08 15:10)

  Args:
    results: MemoryStore.retrieve() 返回的 (Document, score) 列表

  Returns:
    格式化后的文本，无结果时返回空字符串
  """
  if not results:
    return ""

  lines = ["【相关记忆】"]
  for doc, _score in results:
    category_value = doc.metadata.get("category", "")
    timestamp = doc.metadata.get("timestamp", "")

    # 尝试获取中文类别名
    try:
      category_label = MemoryCategory(category_value).display_name
    except ValueError:
      category_label = category_value

    # 截断时间戳到分钟（去掉秒）
    short_time = timestamp[:16] if len(timestamp) >= 16 else timestamp

    lines.append(f"- [{category_label}] {doc.page_content} ({short_time})")

  return "\n".join(lines)


def format_memories_compact(results: list[tuple[Document, float]]) -> str:
  """
  将检索结果格式化为紧凑格式（仅内容，分号分隔）

  格式示例：
    用户喜欢打篮球；曾讨论过NBA总决赛

  Args:
    results: MemoryStore.retrieve() 返回的 (Document, score) 列表

  Returns:
    紧凑格式文本，无结果时返回空字符串
  """
  if not results:
    return ""

  contents = [doc.page_content for doc, _score in results]
  return "；".join(contents)
