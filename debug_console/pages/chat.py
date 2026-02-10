"""
模拟直播间页面
支持单用户和多用户（随机身份）两种模式
"""

from datetime import datetime

from coolname import generate
from nicegui import ui, context

from streaming_studio import StreamingStudio, Comment


def _random_identity() -> tuple[str, str]:
  """
  生成随机用户身份

  Returns:
    (user_id, nickname)
  """
  words = generate(2)
  user_id = "_".join(w.lower() for w in words)
  nickname = " ".join(w.capitalize() for w in words)
  return user_id, nickname


def create_chat_page(studio: StreamingStudio) -> None:
  """
  构建模拟直播间 UI

  Args:
    studio: 直播间实例
  """
  # 页面局部状态
  state = {
    "multi_user": True,
    "user_id": "test_user",
    "nickname": "测试用户",
    "next_id": "",
    "next_nick": "",
  }
  # 预生成第一个随机身份
  state["next_id"], state["next_nick"] = _random_identity()

  # 注册回复回调的引用（stop 时需要移除）
  callback_ref = {"fn": None}

  with ui.column().classes("w-full h-full p-4 gap-4"):
    # 控制栏
    with ui.row().classes("w-full items-center gap-4 flex-wrap"):
      ui.label("模拟直播间").classes("text-2xl font-bold")

      status_label = ui.label().classes("text-sm")

      ui.space()

      async def on_start():
        await studio.start()
        status_label.text = "运行中"
        start_btn.disable()
        stop_btn.enable()

      async def on_stop():
        if callback_ref["fn"]:
          studio.remove_callback(callback_ref["fn"])
          callback_ref["fn"] = None
        await studio.stop()
        status_label.text = "已停止"
        start_btn.enable()
        stop_btn.disable()

      start_btn = ui.button("启动", on_click=on_start).props("dense")
      stop_btn = ui.button("停止", on_click=on_stop).props("dense")
      stop_btn.disable()

    # 用户模式切换
    with ui.row().classes("w-full items-center gap-4 flex-wrap"):
      def on_mode_change(e):
        is_multi = e.value == "multi"
        state["multi_user"] = is_multi
        single_inputs.set_visibility(not is_multi)
        identity_preview.set_visibility(is_multi)
        if is_multi:
          state["next_id"], state["next_nick"] = _random_identity()
          preview_label.text = f"下一个身份: {state['next_nick']} ({state['next_id']})"

      ui.toggle(
        {"single": "单用户", "multi": "多用户（随机）"},
        value="multi",
        on_change=on_mode_change,
      ).props("dense")

      single_inputs = ui.row().classes("gap-2")
      single_inputs.set_visibility(False)
      with single_inputs:
        uid_input = ui.input("用户ID", value="test_user").props("dense").classes("w-32")
        nick_input = ui.input("昵称", value="测试用户").props("dense").classes("w-32")

        def on_uid_change(e):
          state["user_id"] = e.value
        def on_nick_change(e):
          state["nickname"] = e.value
        uid_input.on("update:model-value", on_uid_change)
        nick_input.on("update:model-value", on_nick_change)

      identity_preview = ui.row()
      with identity_preview:
        preview_label = ui.label(
          f"下一个身份: {state['next_nick']} ({state['next_id']})"
        ).classes("text-sm text-gray-500")

    ui.separator()

    # 聊天消息区域（使用 scroll_area 支持滚动控制）
    with ui.scroll_area().classes(
      "w-full flex-1 bg-gray-50 rounded border"
    ).style("height: calc(100vh - 350px); min-height: 300px") as scroll_area:
      chat_container = ui.column().classes("w-full gap-2 p-2")

    def add_comment_bubble(nickname: str, content: str, timestamp: str):
      """添加弹幕气泡（右侧）"""
      with chat_container:
        with ui.row().classes("w-full justify-end"):
          with ui.column().classes("items-end gap-0"):
            ui.label(f"{nickname}  {timestamp}").classes("text-xs text-gray-400")
            ui.chat_message(
              content,
              name=nickname,
              sent=True,
            )
      # 自动滚动到底部
      scroll_area.scroll_to(percent=1.0)

    def add_response_bubble(content: str):
      """添加主播回复气泡（左侧）"""
      with chat_container:
        with ui.row().classes("w-full justify-start"):
          ui.chat_message(
            content,
            name="主播",
            sent=False,
            stamp=datetime.now().strftime("%H:%M:%S"),
          )
      # 自动滚动到底部
      scroll_area.scroll_to(percent=1.0)

    # 注册主播回复回调
    def on_response(response):
      add_response_bubble(response.content)

    callback_ref["fn"] = on_response
    studio.on_response(on_response)

    # 客户端断开时自动清理回调，防止泄漏
    def cleanup():
      if callback_ref["fn"]:
        studio.remove_callback(callback_ref["fn"])
        callback_ref["fn"] = None

    context.client.on_disconnect(cleanup)

    # 输入栏
    with ui.row().classes("w-full gap-2"):
      msg_input = ui.input(placeholder="输入弹幕...").props(
        "dense outlined"
      ).classes("flex-1")

      def send():
        content = msg_input.value.strip()
        if not content or not studio.is_running:
          return

        # 确定身份
        if state["multi_user"]:
          user_id = state["next_id"]
          nickname = state["next_nick"]
        else:
          user_id = state["user_id"] or "test_user"
          nickname = state["nickname"] or "测试用户"

        now = datetime.now()
        comment = Comment(
          user_id=user_id,
          nickname=nickname,
          content=content,
        )
        studio.send_comment(comment)
        add_comment_bubble(nickname, content, now.strftime("%H:%M:%S"))

        msg_input.value = ""

        # 多用户模式：预生成下一个身份
        if state["multi_user"]:
          state["next_id"], state["next_nick"] = _random_identity()
          preview_label.text = f"下一个身份: {state['next_nick']} ({state['next_id']})"

      send_btn = ui.button("发送", on_click=send).props("dense")
      msg_input.on("keydown.enter", send)
