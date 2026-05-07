"""
黑话与标签系统数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class JargonEntry:
  """已知黑话条目"""

  entry_id: str
  phrase: str
  brief: str
  details: str
  tags: tuple[str, ...] = field(default_factory=tuple)
  examples: tuple[str, ...] = field(default_factory=tuple)
  status: str = "known"
  confidence: float = 0.5
  weight: float = 1.0
  last_decay_at: datetime = field(default_factory=datetime.now)
  source_refs: tuple[str, ...] = field(default_factory=tuple)
  version: int = 1
  created_at: datetime = field(default_factory=datetime.now)
  updated_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class PendingJargon:
  """待解明黑话条目"""

  phrase: str
  candidate_brief: str = ""
  candidate_tags: tuple[str, ...] = field(default_factory=tuple)
  notes: str = ""
  seen_count: int = 1
  asked_count: int = 0
  status: str = "pending"
  first_seen_at: datetime = field(default_factory=datetime.now)
  last_seen_at: datetime = field(default_factory=datetime.now)
  last_asked_at: datetime | None = None


@dataclass(frozen=True)
class TagEntry:
  """标签条目"""

  name: str
  definition: str
  examples: tuple[str, ...] = field(default_factory=tuple)
  canonical_quotes: tuple[str, ...] = field(default_factory=tuple)
  related_tags: tuple[str, ...] = field(default_factory=tuple)
  confidence: float = 0.5
  created_at: datetime = field(default_factory=datetime.now)
  updated_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class StreamerTagState:
  """主播标签状态"""

  active_tags: tuple[str, ...] = field(default_factory=tuple)
  candidate_tags: tuple[str, ...] = field(default_factory=tuple)
  rotation_cursor: int = 0
  last_rotate_at: datetime | None = None


@dataclass(frozen=True)
class JargonDecision:
  """一次判官分析的摘要结果"""

  new_pending_count: int = 0
  resolved_count: int = 0
  revised_count: int = 0
  notes: str = ""
  analyzed_at: datetime = field(default_factory=datetime.now)
