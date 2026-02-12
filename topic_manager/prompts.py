"""
话题管理器提示词常量
用于弹幕分类、回复后分析等 LLM 调用
"""

# 单条弹幕分类 prompt
# 输入：话题列表 + 单条弹幕
# 输出：topic_id 或 "none"
SINGLE_CLASSIFY_PROMPT = (
  "当前直播间话题列表：\n{topic_list}\n\n"
  "新弹幕：{comment_content}\n\n"
  "这条弹幕属于哪个话题？只输出 topic_id，如果不属于任何话题输出 none。"
)

# 批量弹幕分类 prompt
# 输入：话题列表 + 多条弹幕
# 输出：JSON 格式的 {comment_id: topic_id} 映射
BATCH_CLASSIFY_PROMPT = (
  "当前直播间话题列表：\n{topic_list}\n\n"
  "以下弹幕需要分类到话题：\n{comments}\n\n"
  "将每条弹幕分类到最相关的话题。如果不属于任何话题，标记为 none。\n"
  "只输出 JSON 格式，键为弹幕编号，值为 topic_id 或 none。例如：\n"
  '  {{"1": "game_discussion", "2": "none", "3": "greeting"}}'
)

# 回复后内容分析 prompt（任务 A）
# 判断话题进度、新话题、跟进建议
CONTENT_ANALYSIS_PROMPT = (
  "你是一个直播间话题顾问。分析以下直播片段，给出话题管理建议。\n\n"
  "【当前话题表】\n{topic_table}\n\n"
  "【最近弹幕】\n{recent_comments}\n\n"
  "【主播回复】\n{response}\n\n"
  "请判断：\n"
  "1. 哪些话题的进度需要更新？给出新的进度描述。\n"
  "2. 是否出现了新话题？如果有，给出 topic_id（snake_case）和初始描述。\n"
  "3. 哪些话题可以继续跟进？给出跟进建议（以第三方顾问视角）。\n\n"
  "只输出 JSON 格式：\n"
  '{{\n'
  '  "progress_updates": {{"topic_id": "新进度描述"}},\n'
  '  "new_topics": [{{"topic_id": "xxx", "progress": "描述", "suggestion": "建议"}}],\n'
  '  "suggestion_updates": {{"topic_id": "新的跟进建议"}}\n'
  '}}'
)

# 回复后节奏分析 prompt（任务 B）
# 判断过期话题、建议等待时间
RHYTHM_ANALYSIS_PROMPT = (
  "你是一个直播节奏顾问。分析当前直播的节奏，给出建议。\n\n"
  "【当前话题表】\n{topic_table}\n\n"
  "【最近弹幕】\n{recent_comments}\n\n"
  "【主播回复】\n{response}\n\n"
  "请判断：\n"
  "1. 哪些话题已经聊了太久，应该切换？列出 topic_id。\n"
  "2. 根据当前谈话内容和节奏，主播下次回复前应该等多久？\n"
  "   - 如果主播抛出了问题 → 等久一点（8-15秒）让观众回答\n"
  "   - 如果主播在回应具体弹幕 → 快节奏（3-8秒）\n"
  "   - 如果话题进入尾声 → 适当放缓（10-20秒）\n\n"
  "只输出 JSON 格式：\n"
  '{{\n'
  '  "stale_topic_ids": ["topic_id_1"],\n'
  '  "suggested_min_wait": 5.0,\n'
  '  "suggested_max_wait": 12.0\n'
  '}}'
)
