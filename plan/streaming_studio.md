# streaming_studio 模块计划

## 模块职责

虚拟直播间核心，管理弹幕缓冲、双轨定时器、LLM调用和回复分发。

## 文件结构

```
streaming_studio/
├── __init__.py               # 模块导出
├── models.py                 # Comment, StreamerResponse 数据模型
├── database.py               # SQLite弹幕存储
├── studio.py                 # StreamingStudio 异步核心类
├── test_chatter_studio.py    # 命令行测试（单用户）
└── test_danmaku_studio.py    # 弹幕模拟测试（随机用户身份）
```

## 数据模型

### Comment (弹幕)

```python
@dataclass
class Comment:
  id: str              # 唯一ID
  user_id: str         # 用户ID
  nickname: str        # 用户昵称
  content: str         # 弹幕内容
  timestamp: datetime  # 发送时间
```

### StreamerResponse (主播回复)

```python
@dataclass
class StreamerResponse:
  id: str              # 唯一ID
  content: str         # 回复内容
  reply_to: list[str]  # 回复的弹幕ID列表
  timestamp: datetime  # 回复时间
```

## 核心类

### CommentDatabase

SQLite存储，保存弹幕和回复记录。

```python
class CommentDatabase:
  def __init__(db_path)
  def save_comment(comment)
  def save_response(response)
  def get_recent_comments(limit) -> list[Comment]
```

### StreamingStudio

异步主循环，双轨定时器驱动的回复触发机制。

#### 构造参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm_wrapper` | LLMWrapper | - | LLM 调用封装 |
| `database` | CommentDatabase | - | 弹幕数据库 |
| `recent_comments_limit` | int | 20 | 每次触发时收集的最近弹幕数上限 |
| `min_interval` | float | 1.0 | 随机等待下限（秒） |
| `max_interval` | float | 10.0 | 随机等待上限（秒） |

#### 双轨定时器机制

核心思想：**定时器 + 弹幕加速**

```
每次回复间隔 = random(min_interval, max_interval)
当有新弹幕到达时：剩余等待时间 -= 弹幕数量
```

实现细节：
- 使用 `deque[Comment]` (maxlen=200) 作为环形缓冲区
- 使用 `asyncio.Event` 通知新弹幕到达
- 根据 `_last_reply_time` 将弹幕分为"旧弹幕"和"新弹幕"
- 格式化时标注相对时间（如"35秒前"）和绝对时间（如"14:23:05"）
- 检测沉默状态，当无新弹幕时计算并显示距上次弹幕的秒数

#### 方法列表

```python
class StreamingStudio:
  def __init__(llm_wrapper, database, recent_comments_limit, min_interval, max_interval)

  # 生命周期
  async def start()
  async def stop()

  # 弹幕接收
  def send_comment(comment: Comment)

  # 回复获取
  async def get_response(timeout=None) -> StreamerResponse

  # 回调机制
  def on_response(callback: Callable[[StreamerResponse], None])
  def remove_callback(callback)

  # 调试监控
  def debug_state() -> dict
  def get_stats() -> dict
```

#### 弹幕格式化

单条弹幕格式：
```
[14:23:05 / 35秒前] 花凛 (id: user_abc): 主播唱首歌
```

组合 prompt 格式：
```
【上次回复前的弹幕（背景参考）】
- [14:22:00 / 3分35秒前] 小明 (id: u001): 你好
- [14:22:30 / 3分5秒前] 小红 (id: u002): 刚来

【上次回复后的新弹幕】
- [14:25:00 / 35秒前] 小明 (id: u001): 主播唱歌
- [14:25:20 / 15秒前] 小蓝 (id: u003): 好耶
```

沉默检测：
```
【上次回复后无人说话】
（已经 45 秒没人说话了）
```

## 核心特性

### 双轨定时器

模拟真人主播"隔一会儿说一句，有人刷屏就加快节奏"的自然行为：
- 基础节奏：每次回复后等待 random(1s, 10s)
- 加速机制：每条新弹幕到达时减少剩余等待 1 秒
- 避免被动触发：不再完全依赖"收到弹幕才回复"

### 时间观念

- 每条弹幕标注绝对时间 + 相对时间
- 区分"旧弹幕（背景）"和"新弹幕（需回复）"
- 检测沉默状态，提示 AI 主动活跃气氛
- base_instruction.txt 中增加时间观念指导

### 弹幕缓冲区

- 使用 deque(maxlen=200) 保留历史上下文
- 支持回看最近弹幕，提供更丰富的背景信息
- 每次触发时取最近 20 条弹幕

## 测试工具

### test_chatter_studio.py
单用户命令行测试，手动输入弹幕。

### test_danmaku_studio.py
多用户弹幕模拟测试：
- 使用 coolname 库生成随机用户身份
- 每条弹幕自动分配不同用户 ID 和昵称
- 验证 AI 对多用户场景的适应能力

## 状态

- [x] 数据模型定义
- [x] 数据库实现
- [x] StreamingStudio 核心实现
- [x] 双轨定时器机制
- [x] 弹幕格式化（时间标注）
- [x] 沉默检测
- [x] debug_state() 调试接口
- [x] 命令行测试（单用户）
- [x] 弹幕模拟测试（随机用户）
