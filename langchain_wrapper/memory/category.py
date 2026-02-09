"""
记忆类别枚举
定义 RAG 记忆系统支持的记忆分类
"""

from enum import Enum


# 类别 -> 中文显示名映射
_DISPLAY_NAMES = {
  "user_preference": "用户偏好",
  "topic": "话题",
  "interaction": "互动事件",
  "fact": "事实信息",
  "emotion": "情感记录",
}


class MemoryCategory(Enum):
  """记忆类别枚举"""

  USER_PREFERENCE = "user_preference"  # 用户偏好
  TOPIC = "topic"                      # 话题记录
  INTERACTION = "interaction"          # 互动事件
  FACT = "fact"                        # 事实性信息
  EMOTION = "emotion"                  # 情感记录

  @property
  def display_name(self) -> str:
    """获取中文显示名"""
    return _DISPLAY_NAMES[self.value]
