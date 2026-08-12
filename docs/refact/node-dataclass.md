# Node 类型化

将 node dict 改为 dataclass，消除魔法字符串。

目标：
```python
@dataclass
class Node:
    id: int
    name: str
    address: str
    port: int
    protocol: str
    bin_type: str
    config_json: str     # 保持字符串，懒解析
    sub_id: int = 0
```

优点：IDE 补全、类型检查、字段清晰、DB row `**row` 一行映射。

代价：全项目 `node['field']` → `node.field` 改动。

建议：单独 MR，不在当前 refact 分支做。
