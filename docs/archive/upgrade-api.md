# 升级 API 路由设计

> Archive: historical design document; not the current implementation status.

> 层级：路由层。承接 [singbox/upgrade.py](../../app/singbox/upgrade.py) 的下载/升级逻辑。
> 状态：⏳ 待确认。

## 1. 背景

`app/singbox/upgrade.py` 已就绪，提供三个函数：
- `get_version()` → 当前版本字符串（`'N/A'` 若不存在）
- `check_upgrade()` → `{success, current_version, latest_version, download_url, asset_name, is_update}`
- `download_upgrade()` → 下载 + 解压 → `{success, message, version}`

但没有 HTTP 端点暴露这些能力。v2 只有 sing-box 一个引擎，路由比 v1 简单——不需 `{bin_name}` 参数。

## 2. 路由设计

| 方法 | 路径 | 处理函数 | 说明 |
|------|------|---------|------|
| GET | `/api/upgrade/status` | `upgrade_status` | 当前版本 + 是否可更新（check_upgrade 的轻量包装） |
| POST | `/api/upgrade/download` | `upgrade_download` | 下载最新版本 + 解压到 `data/bin/` |

v1 有两个端点（check + download），合并为 `status` + `download`：
- `status` 比 `check` 语义更准确——返回当前版本 + 最新版本，前端据此显示"已是最新"或"有更新"
- `download` 下载后**不自动重启**（upgrade.py 的设计决策：只落二进制，启停交给调用方）

### 2.1 GET `/api/upgrade/status`

```python
@bp.route('/api/upgrade/status', methods=['GET'])
def upgrade_status():
    """当前 sing-box 版本 + 最新 release 信息。"""
    r = upgrade.check_upgrade()
    if not r['success']:
        return jsonify(r), 502  # GitHub API 不可达
    return jsonify(r)
```

**返回示例：**
```json
{
    "success": true,
    "current_version": "1.13.19",
    "latest_version": "1.14.0",
    "download_url": "https://github.com/...",
    "asset_name": "sing-box-1.14.0-linux-amd64.tar.gz",
    "is_update": true
}
```

已是最新时 `is_update: false`，`download_url` 可能为 `null`（GitHub 无匹配 asset）。

### 2.2 POST `/api/upgrade/download`

```python
@bp.route('/api/upgrade/download', methods=['POST'])
def upgrade_download():
    """下载最新 sing-box 二进制。不自动重启。"""
    r = upgrade.download_upgrade()
    if not r['success']:
        return jsonify(r), 502
    return jsonify(r)
```

**返回示例：**
```json
{"success": true, "message": "Upgraded to 1.14.0", "version": "1.14.0"}
```

已是最新时：
```json
{"success": true, "message": "Already up to date", "version": "1.13.19"}
```

### 2.3 升级后重启

前端拿到 `success` + 新版本后，调 `POST /api/restart`（已有，[routes.md](routes.md)）重启 sing-box 使用新二进制。**不自动重启**的理由：upgrade.py 设计决策——只落二进制，启停由调用方控制，避免升级失败时连带重启失败。

## 3. 错误处理

| 场景 | HTTP | 返回 |
|------|------|------|
| GitHub API 不可达 | 502 | `{success: false, message: 'GitHub API error: ...'}` |
| 无匹配 asset | 200 | `{success: false, message: 'No matching asset found'}` |
| 下载超时 | 502 | `{success: false, message: 'Download failed: ...'}` |
| 解压失败 | 502 | `{success: false, message: 'Extraction failed: ...'}` |

## 4. 实现要点

- 注册在现有 `bp = Blueprint('api', ...)`，不新建蓝图
- `check_upgrade()` 内部调 GitHub API（timeout=15），可能慢——前端应显示 loading
- `download_upgrade()` 下载整个 release 包（timeout=120），**更慢**——前端必须显示进度/加载态
- 下载后二进制在 `data/bin/sing-box`（`SINGBOX_BIN_PATH` 常量）
- 不做二进制校验（v1 也没有）
- 不碰现有 `test/`

## 5. 验证

1. `GET /api/upgrade/status` → 返回 current_version + latest_version
2. `POST /api/upgrade/download` → 若有新版本，检查 `data/bin/sing-box` 更新时间
3. `POST /api/restart` → sing-box 重启使用新版本
4. `GET /api/upgrade/status` → `is_update: false`（已是最新）
