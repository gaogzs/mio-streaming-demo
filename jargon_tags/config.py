"""
黑话与标签系统配置
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class JargonTagsConfig:
  """黑话与标签系统配置"""

  # 模式切换: reference / polish
  mode: str = "reference"

  # 黑话判官周期分析
  analysis_interval_seconds: float = 30.0
  comment_window_size: int = 30
  enable_llm_judge: bool = True
  llm_related_known_limit: int = 12
  llm_pending_limit: int = 20

  # 待解明追问策略
  pending_question_max_per_reply: int = 2
  pending_question_pick_mode: str = "random_k"  # random_k / model_decide
  pending_abandon_threshold: int = 3

  # 标签轮换
  tag_rotation_interval_seconds: float = 600.0
  active_tag_count: int = 3
  min_tag_confidence: float = 0.55

  # 检索权重
  retrieval_top_k: int = 8
  retrieval_min_score: float = 0.12
  exact_match_boost: float = 1.8
  vector_match_boost: float = 1.0
  tag_match_boost: float = 1.2
  indirect_tag_match_boost: float = 1.05
  tag_mismatch_penalty: float = 0.92

  # 已知条目修订阈值
  revision_confidence_threshold: float = 0.85

  # 衰减策略
  weight_decay_coefficient: float = 0.95  # 以天为单位的衰减底数
  weight_archive_threshold: float = 0.05  # 当 weight 衰减到低于该值时转入归档
