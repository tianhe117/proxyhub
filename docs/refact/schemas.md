# 公用结构体（schemas）层

跨层共享的数据结构集中到 `app/utils/schemas.py`，全项目 `from app.utils import CheckResult` 单一来源。

## 目标

```
app/utils/
├── schemas.py     # CheckResult — 公用结构体
└── __init__.py    # 聚合导出
```

## 结构体

### CheckResult（已搬家）

```python
@dataclass
class CheckResult:
    success: bool
    tcp_latency_ms: int
    url_latency_ms: int
    http_code: str
    error: str
```

从 `app/checker/model.py` 迁入；调用方统一 `from app.utils import CheckResult`，`app.checker` 不再 re-export。

## 依赖

`schemas.py` 只依赖 stdlib（`dataclasses`），是 `common.py` 同级的叶子模块。依赖方向单向：`db / engine / services / checker` → `utils` → `settings`，无环。

## Node 不类型化

`node` 保持 `sqlite3.Row` / 裸 dict，不建 dataclass / TypedDict。字段说明以 `app/db/node.py` 顶部的注释为单一来源（`node['field']` 访问）。理由：单人 + Claude 辅助开发的项目里，dataclass 的 IDE 补全 / 静态类型检查收益不成立，反而要维护多处同步、多一层边界转换。
