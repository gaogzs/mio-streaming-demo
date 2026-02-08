"""
数据库模块
使用 SQLite 存储弹幕和回复记录
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Comment, StreamerResponse


class CommentDatabase:
  """
  弹幕数据库
  使用 SQLite 存储弹幕和主播回复
  """

  def __init__(self, db_path: Optional[Path] = None):
    """
    初始化数据库

    Args:
      db_path: 数据库文件路径，默认为项目根目录下的 data/comments.db
    """
    if db_path is None:
      project_root = Path(__file__).parent.parent
      data_dir = project_root / "data"
      data_dir.mkdir(exist_ok=True)
      db_path = data_dir / "comments.db"

    self.db_path = Path(db_path)
    self._init_database()

  def _get_connection(self) -> sqlite3.Connection:
    """获取数据库连接"""
    return sqlite3.connect(str(self.db_path))

  def _init_database(self) -> None:
    """初始化数据库表"""
    with self._get_connection() as conn:
      cursor = conn.cursor()

      # 创建弹幕表
      cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          nickname TEXT NOT NULL,
          content TEXT NOT NULL,
          timestamp TEXT NOT NULL
        )
      """)

      # 创建回复表
      cursor.execute("""
        CREATE TABLE IF NOT EXISTS responses (
          id TEXT PRIMARY KEY,
          content TEXT NOT NULL,
          reply_to TEXT NOT NULL,
          timestamp TEXT NOT NULL
        )
      """)

      # 创建索引
      cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_comments_timestamp
        ON comments(timestamp)
      """)
      cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_responses_timestamp
        ON responses(timestamp)
      """)

      conn.commit()

  def save_comment(self, comment: Comment) -> None:
    """
    保存弹幕

    Args:
      comment: 弹幕对象
    """
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
        """
        INSERT OR REPLACE INTO comments (id, user_id, nickname, content, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
          comment.id,
          comment.user_id,
          comment.nickname,
          comment.content,
          comment.timestamp.isoformat()
        )
      )
      conn.commit()

  def save_response(self, response: StreamerResponse) -> None:
    """
    保存主播回复

    Args:
      response: 回复对象
    """
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
        """
        INSERT OR REPLACE INTO responses (id, content, reply_to, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
          response.id,
          response.content,
          json.dumps(list(response.reply_to)),
          response.timestamp.isoformat()
        )
      )
      conn.commit()

  def get_comment(self, comment_id: str) -> Optional[Comment]:
    """
    根据ID获取弹幕

    Args:
      comment_id: 弹幕ID

    Returns:
      弹幕对象，不存在则返回None
    """
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
        "SELECT id, user_id, nickname, content, timestamp FROM comments WHERE id = ?",
        (comment_id,)
      )
      row = cursor.fetchone()

      if row is None:
        return None

      return Comment(
        id=row[0],
        user_id=row[1],
        nickname=row[2],
        content=row[3],
        timestamp=datetime.fromisoformat(row[4])
      )

  def get_recent_comments(self, limit: int = 10) -> list[Comment]:
    """
    获取最近的弹幕

    Args:
      limit: 返回数量限制

    Returns:
      弹幕列表，按时间倒序
    """
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
        """
        SELECT id, user_id, nickname, content, timestamp
        FROM comments
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,)
      )
      rows = cursor.fetchall()

      return [
        Comment(
          id=row[0],
          user_id=row[1],
          nickname=row[2],
          content=row[3],
          timestamp=datetime.fromisoformat(row[4])
        )
        for row in rows
      ]

  def get_recent_responses(self, limit: int = 10) -> list[StreamerResponse]:
    """
    获取最近的回复

    Args:
      limit: 返回数量限制

    Returns:
      回复列表，按时间倒序
    """
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute(
        """
        SELECT id, content, reply_to, timestamp
        FROM responses
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,)
      )
      rows = cursor.fetchall()

      return [
        StreamerResponse(
          id=row[0],
          content=row[1],
          reply_to=tuple(json.loads(row[2])),
          timestamp=datetime.fromisoformat(row[3])
        )
        for row in rows
      ]

  def get_comment_count(self) -> int:
    """获取弹幕总数"""
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT COUNT(*) FROM comments")
      return cursor.fetchone()[0]

  def get_response_count(self) -> int:
    """获取回复总数"""
    with self._get_connection() as conn:
      cursor = conn.cursor()
      cursor.execute("SELECT COUNT(*) FROM responses")
      return cursor.fetchone()[0]
