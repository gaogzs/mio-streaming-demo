"""
监控面板页面
实时显示后台各模块运行状态
"""

from nicegui import ui

from debug_console.state_collector import StateCollector


def create_monitor_page(collector: StateCollector) -> None:
  """
  构建监控面板 UI

  Args:
    collector: 状态收集器
  """
  # 用于存放可刷新组件的容器引用
  containers = {}

  def refresh():
    """定时刷新回调"""
    try:
      state = collector.snapshot()
      _update_studio_card(containers.get("studio"), state.get("studio"))
      _update_memory_card(containers.get("memory"), state.get("memory"))
      _update_llm_card(containers.get("llm"), state.get("llm"))
      _update_prompt_card(containers.get("prompt"), state.get("studio"))
    except Exception:
      pass  # 刷新失败时静默跳过，等待下次重试

  with ui.column().classes("w-full gap-4 p-4"):
    # 标题栏
    with ui.row().classes("w-full items-center justify-between"):
      ui.label("实时监控").classes("text-2xl font-bold")
      ui.button("手动刷新", on_click=refresh).props("flat dense")

    # 上排：直播间 + 记忆系统
    with ui.row().classes("w-full gap-4"):
      containers["studio"] = _build_studio_card()
      containers["memory"] = _build_memory_card()

    # 下排：LLM 状态
    with ui.row().classes("w-full gap-4"):
      containers["llm"] = _build_llm_card()

    # 最近 prompt 展示
    containers["prompt"] = _build_prompt_card()

  # 每 2 秒自动刷新
  ui.timer(2.0, refresh)


# ============================================================
# 卡片构建函数
# ============================================================

def _build_studio_card() -> dict:
  """构建直播间状态卡片，返回可更新的组件引用"""
  refs = {}
  with ui.card().classes("flex-1 min-w-[400px]"):
    ui.label("直播间状态").classes("text-lg font-bold")
    ui.separator()
    with ui.column().classes("gap-1"):
      refs["running"] = ui.label()
      refs["interval"] = ui.label()
      refs["buffer"] = ui.label()
      refs["pending"] = ui.label()
      refs["last_reply"] = ui.label()
      refs["totals"] = ui.label()
    ui.separator()
    ui.label("最近弹幕").classes("font-bold text-sm")
    refs["comments"] = ui.column().classes("gap-0 max-h-[200px] overflow-auto")
  return refs


def _build_memory_card() -> dict:
  """构建记忆系统卡片"""
  refs = {}
  with ui.card().classes("flex-1 min-w-[400px]"):
    ui.label("记忆系统").classes("text-lg font-bold")
    ui.separator()
    with ui.column().classes("gap-1"):
      refs["active_bar"] = ui.linear_progress(value=0, show_value=False).classes("w-full")
      refs["active_label"] = ui.label()
      refs["layers"] = ui.label()
      refs["interactions"] = ui.label()
      refs["tasks"] = ui.label()
    ui.separator()
    ui.label("Active 层内容").classes("font-bold text-sm")
    refs["active_list"] = ui.column().classes("gap-0 max-h-[200px] overflow-auto")
  return refs


def _build_llm_card() -> dict:
  """构建 LLM 状态卡片"""
  refs = {}
  with ui.card().classes("flex-1 min-w-[400px]"):
    ui.label("LLM 状态").classes("text-lg font-bold")
    ui.separator()
    with ui.column().classes("gap-1"):
      refs["model"] = ui.label()
      refs["persona"] = ui.label()
      refs["history"] = ui.label()
      refs["memory"] = ui.label()
      refs["bg_tasks"] = ui.label()
  return refs


def _build_prompt_card() -> dict:
  """构建最近 prompt 卡片"""
  refs = {}
  with ui.card().classes("w-full"):
    ui.label("最近一次发给模型的 Prompt").classes("text-lg font-bold")
    ui.separator()
    refs["prompt_text"] = ui.code("（等待首次触发）", language="markdown").classes(
      "w-full max-h-[300px] overflow-auto"
    )
  return refs


# ============================================================
# 卡片更新函数
# ============================================================

def _update_studio_card(refs: dict, state: dict) -> None:
  """更新直播间状态卡片"""
  if not refs or not state:
    return

  status = "运行中" if state["is_running"] else "已停止"
  refs["running"].text = f"状态: {status}"
  refs["interval"].text = (
    f"触发间隔: {state['min_interval']:.1f}s ~ {state['max_interval']:.1f}s"
  )
  refs["buffer"].text = (
    f"弹幕缓冲: {state['buffer_size']} / {state['buffer_max']}"
  )
  refs["pending"].text = f"待处理弹幕: {state['pending_comment_count']}"
  refs["last_reply"].text = (
    f"上次回复: {state['last_reply_time'] or '无'}"
  )
  refs["totals"].text = (
    f"累计弹幕: {state['total_comments']}  累计回复: {state['total_responses']}"
  )

  # 更新弹幕列表
  comments_container = refs["comments"]
  comments_container.clear()
  with comments_container:
    for c in reversed(state["recent_comments"]):
      ui.label(
        f"[{c['timestamp']}] {c['nickname']}: {c['content']}"
      ).classes("text-xs text-gray-600")


def _update_memory_card(refs: dict, state: dict) -> None:
  """更新记忆系统卡片"""
  if not refs:
    return

  if state is None:
    refs["active_label"].text = "记忆系统未启用"
    refs["layers"].text = ""
    refs["interactions"].text = ""
    refs["tasks"].text = ""
    refs["active_bar"].value = 0
    return

  capacity = state["active_capacity"]
  count = state["active_count"]
  refs["active_bar"].value = count / capacity if capacity > 0 else 0
  refs["active_label"].text = f"Active 层: {count} / {capacity}"
  refs["layers"].text = (
    f"Temporary: {state['temporary_count']}  "
    f"Summary: {state['summary_count']}  "
    f"Static: {state['static_count']}"
  )
  refs["interactions"].text = f"近期交互缓冲: {state['recent_interactions']}"

  summary_status = "运行中" if state["summary_task_running"] else "停止"
  cleanup_status = "运行中" if state["cleanup_task_running"] else "停止"
  refs["tasks"].text = f"汇总任务: {summary_status}  清理任务: {cleanup_status}"

  # 更新 active 层内容列表
  active_list = refs["active_list"]
  active_list.clear()
  with active_list:
    for m in state["active_memories"]:
      ui.label(
        f"[{m['timestamp']}] {m['content']}"
      ).classes("text-xs text-gray-600")


def _update_llm_card(refs: dict, state: dict) -> None:
  """更新 LLM 状态卡片"""
  if not refs or not state:
    return

  refs["model"].text = f"模型: {state['model_type']} ({state['model_name'] or '默认'})"
  refs["persona"].text = f"角色: {state['persona']}"
  refs["history"].text = f"对话历史: {state['history_length']} 轮"
  refs["memory"].text = f"记忆功能: {'已启用' if state['has_memory'] else '未启用'}"
  refs["bg_tasks"].text = f"后台任务: {state['background_tasks']}"


def _update_prompt_card(refs: dict, state: dict) -> None:
  """更新 prompt 展示卡片"""
  if not refs or not state:
    return

  prompt = state.get("last_prompt")
  refs["prompt_text"].content = prompt if prompt else "（等待首次触发）"
