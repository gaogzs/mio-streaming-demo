# prompts 模块计划

## 模块职责

提供提示词加载和管理功能，支持主播基础指令和人设切换。

## 文件结构

```
prompts/
├── __init__.py           # 模块导出
├── prompt_loader.py      # PromptLoader类
├── base_instruction.txt  # 主播基础指令
├── persona_karin.txt     # 人设1: 元气偶像少女
├── persona_sage.txt      # 人设2: 知性学者
└── persona_kuro.txt      # 人设3: 酷酷游戏主播
```

## 核心类: PromptLoader

### 方法

| 方法 | 说明 |
|------|------|
| `load(filename)` | 加载指定提示词文件 |
| `get_base_instruction()` | 获取基础指令 |
| `get_persona(name)` | 获取人设提示词 (karin/sage/kuro) |
| `get_full_system_prompt(persona)` | 基础指令 + 人设组合 |
| `list_personas()` | 列出所有可用人设 |

### 使用示例

```python
from prompts import PromptLoader

loader = PromptLoader()
system_prompt = loader.get_full_system_prompt("karin")
```

## 状态

- [x] 基础指令编写
- [x] 3个人设提示词编写
- [x] PromptLoader类实现
