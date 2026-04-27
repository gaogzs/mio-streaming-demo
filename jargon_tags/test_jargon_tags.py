"""
黑话与标签系统最小测试脚本

运行方式：
  python -m jargon_tags.test_jargon_tags
"""

import asyncio
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from streaming_studio.database import CommentDatabase
from streaming_studio.models import Comment

from jargon_tags import JargonTagsConfig, JargonTagsManager, PendingJargon
from jargon_tags.models import JargonEntry


def _assert(condition: bool, message: str) -> None:
  """简单断言工具"""
  if not condition:
    raise AssertionError(message)


def test_pending_promotion() -> None:
  """验证 pending 达到阈值后会转入 known"""
  db = CommentDatabase(db_path=":memory:")
  cfg = JargonTagsConfig(
    mode="reference",
    enable_llm_judge=False,
    pending_abandon_threshold=2,
  )
  manager = JargonTagsManager(persona="karin", database=db, config=cfg)

  manager._store.upsert_pending(PendingJargon(phrase="理科圣体", asked_count=2))
  manager._promote_abandoned_pending()

  known = manager._store.find_known_by_phrase("理科圣体")
  pending = manager._store.find_pending_by_phrase("理科圣体")

  _assert(known is not None, "pending 未正确转入 known")
  _assert(pending is None, "pending 条目未被清除")


async def test_gradual_tag_rotation() -> None:
  """验证标签低频渐进轮换（每次最多替换一个）"""
  db = CommentDatabase(db_path=":memory:")
  cfg = JargonTagsConfig(
    mode="reference",
    enable_llm_judge=False,
    active_tag_count=3,
    tag_rotation_interval_seconds=0.0,
  )
  manager = JargonTagsManager(persona="karin", database=db, config=cfg)

  manager._tag_state = manager._tag_state.__class__(
    active_tags=("普通网民", "主播粉丝", "90后"),
    candidate_tags=tuple(),
    rotation_cursor=0,
    last_rotate_at=None,
  )

  manager._rotate_active_tags_gradually(("理科生", "贴吧老哥"))
  first = manager._tag_state.active_tags

  manager._rotate_active_tags_gradually(("二次元", "贴吧老哥"))
  second = manager._tag_state.active_tags

  diff1 = sum(1 for a, b in zip(("普通网民", "主播粉丝", "90后"), first) if a != b)
  diff2 = sum(1 for a, b in zip(first, second) if a != b)

  _assert(diff1 <= 1, "第一次轮换替换超过 1 个标签")
  _assert(diff2 <= 1, "第二次轮换替换超过 1 个标签")


async def test_polish_fallback() -> None:
  """验证 polish 模式在无模型可用时回退原回复"""
  db = CommentDatabase(db_path=":memory:")
  cfg = JargonTagsConfig(mode="polish", enable_llm_judge=False)
  manager = JargonTagsManager(persona="karin", database=db, config=cfg, judge_model=None)

  # 填一个黑话条目，避免因为无候选直接返回。
  manager._store.upsert_known(
    JargonEntry(
      entry_id="test_jargon_1",
      phrase="上头",
      brief="非常兴奋",
      details="表示情绪高涨",
      tags=("普通网民",),
    )
  )

  # 模拟模型不可用：覆盖 _get_model 抛异常
  def _raise_model_error():
    raise RuntimeError("mock model unavailable")

  manager._get_model = _raise_model_error  # type: ignore[assignment]

  comments = [
    Comment(user_id="u1", nickname="小明", content="这局太上头了"),
  ]
  original = "我也觉得这把很刺激！"
  rewritten = await manager.polish_response(original, comments)

  _assert(rewritten == original, "polish 回退失败，未返回原回复")


async def main() -> None:
  print("开始运行 jargon_tags 最小测试...")

  test_pending_promotion()
  print("[PASS] pending 迁移")

  await test_gradual_tag_rotation()
  print("[PASS] 标签渐进轮换")

  await test_polish_fallback()
  print("[PASS] polish 回退")

  print("全部测试通过。")


if __name__ == "__main__":
  asyncio.run(main())
