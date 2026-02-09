"""
记忆系统提示词常量
用于交互记录总结和定时汇总的 LLM prompt
"""

# 交互记录总结 prompt
# 将一轮对话总结为第一人称记忆
INTERACTION_SUMMARY_PROMPT = (
  "请将以下对话总结为一条简短的第一人称记忆。\n"
  "用户说：{input}\n"
  "我回复了：{response}\n"
  "请用「我」作为主语，一句话总结这次互动的关键信息。"
  "只输出总结，不要输出其他任何内容。"
)

# 定时汇总 prompt
# 将一段时间内的记忆和互动汇总为摘要
PERIODIC_SUMMARY_PROMPT = (
  "请将以下这段时间的记忆和互动汇总为2-3句话的摘要。\n"
  "【近期记忆】\n{active_memories}\n"
  "【近期互动】\n{recent_interactions}\n"
  "请用「我」作为主语。只输出摘要，不要输出其他任何内容。"
)
