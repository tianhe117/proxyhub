# process 层优化

## 现状

```
app/process/
├── __init__.py   # 空 docstring，不 re-export
└── manager.py    # 381 行，进程生命周期全部实现
```

## 问题

1. **in/out 进程检查重复 4 次**——`is_service_running` 的核心逻辑在 `manager.py`、`api_services.py`、`service_manager.py` 各自实现。
2. **路径拼接忽略 BASE_DIR**——`_get_bin_path` 等 3 处用 `os.path.dirname` 链。
3. **无意义三元表达式**——`name if name != 'sing-box' else name` 恒等，`api_bins.py`、`api_system.py` 各一处。
4. **`__init__.py` 不 re-export**——调用方被迫写 `from app.process.manager import ...`。

## 改动

| 文件 | 操作 |
|------|------|
| `process/manager.py` | 新增 `has_in_and_out(procs)`；`_get_bin_path` 改用 `BASE_DIR` |
| `process/__init__.py` | re-export 全部公开函数 |
| `routes/api_services.py` | 删内联 `_has_in_and_out`，改调 `has_in_and_out` |
| `services/service_manager.py` | 两处内联检查改调 `has_in_and_out`；bin_path 改用 `BASE_DIR` |
| `routes/api_bins.py` | 删无意义三元 |
| `routes/api_system.py` | 删无意义三元 |
| `services/config_service.py` | bin_path 改用 `BASE_DIR` |

## 验证

1. 启动应用，服务列表/系统信息页正常
2. 启动/停止服务，进程状态判断正确
