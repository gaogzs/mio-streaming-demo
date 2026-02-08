# streaming_studio 模块计划

## 模块职责

虚拟直播间核心，管理弹幕队列、LLM调用和回复分发。

## 文件结构

```
streaming_studio/
├── __init__.py             # 模块导出
├── models.py               # Comment, StreamerResponse 数据模型
├── database.py             # SQLite弹幕存储
├── studio.py               # StreamingStudio 异步核心类
└── test_chatter_studio.py  # 命令行测试
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

异步主循环，接收弹幕并生成回复。

```python
class StreamingStudio:
  def __init__(llm_wrapper, database)
  async def start()
  async def stop()
  def send_comment(comment)
  async def get_response() -> StreamerResponse
  def on_response(callback)
```

## 状态

- [x] 数据模型定义
- [x] 数据库实现
- [x] StreamingStudio核心实现
- [x] 命令行测试
