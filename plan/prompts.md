# prompts 模块计划

## 模块职责

提供通用提示词加载功能，通过委托 PersonaLoader 获取角色信息，组装完整的系统提示词。

## 文件结构

```
prompts/
├── __init__.py           # 模块导出
├── prompt_loader.py      # PromptLoader类（委托 PersonaLoader）
└── base_instruction.txt  # 主播基础指令
```

## 核心类: PromptLoader

内部持有 PersonaLoader 实例，负责组装 base_instruction + 角色提示词。

### 方法

| 方法 | 说明 |
|------|------|
| `load(filename)` | 加载指定提示词文件 |
| `get_base_instruction()` | 获取基础指令 |
| `get_full_system_prompt(persona)` | 基础指令 + 角色提示词（委托 PersonaLoader） |
| `list_personas()` | 列出所有可用角色（委托 PersonaLoader） |

### 使用示例

```python
from prompts import PromptLoader

loader = PromptLoader()
system_prompt = loader.get_full_system_prompt("karin")
personas = loader.list_personas()  # ["karin", "kuro", "sage"]
```

### 与 PersonaLoader 的关系

```
PromptLoader
├── 自身: 管理 prompts/ 下的通用文件（base_instruction.txt）
└── 委托 PersonaLoader: 获取角色专属 system_prompt
```

LLMWrapper 只依赖 PromptLoader，不直接使用 PersonaLoader。

## 状态

- [x] 基础指令编写
- [x] PromptLoader类实现
- [x] 与 PersonaLoader 集成
