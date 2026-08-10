# 移动端 Web 前端设计方案

## 目标

为 ProxyHub 接入 iOS/Android 移动端 Web UI，三个页面：Dashboard、Inbounds、Outbounds。完全独立模板，不整合进现有桌面布局。纯手写 CSS + vanilla JS，深色终端风格。

---

## 1. 触发机制

- **User-Agent 匹配**：`Android|iPhone|iPad|iPod|CriOS|FxiOS|Mobile|Silk`
- **Query 参数**：`?mobile=0` 强制桌面版，`?mobile=1` 强制移动版
- **session 持久化**：进入桌面/移动后保持直到退出或参数覆盖

---

## 2. 文件清单

```
新增:
  templates/mobile/base.html       # 移动 shell（CSS, tab bar, toast, modal, 全局 JS）
  templates/mobile/login.html      # 移动登录（独立页面）
  templates/mobile/dashboard.html  # 服务管理
  templates/mobile/inbounds.html   # 入站管理
  templates/mobile/outbounds.html  # 出站管理

修改:
  app/routes/__init__.py           # is_mobile_device()
  app/routes/pages.py              # 按设备分发模板
```

---

## 3. 移动布局（base.html）

```
+------------------------+
| Top Bar      48px      |  ProxyHub  + 当前页按钮
+------------------------+
| Content      flex:1    |  可滚动卡片列表
+------------------------+
| Tab Bar      56px      |  Dashboard | Inbounds | Outbounds
+------------------------+

Toast: 顶部浮动，最多 3 条，3s 消失，左色条标识级别
Modal: 底部 sheet，圆角顶部，滑入动画
```

### CSS 变量（深色终端风）

| 变量 | 值 |
|------|-----|
| `--bg-body` | `#0f0f0f` |
| `--bg-card` | `#1a1a1a` |
| `--border` | `#2a2a2a` |
| `--text` | `#d4d4d4` |
| `--text-secondary` | `#888` |
| `--accent` | `#64b5f6` |
| `--green` | `#81c784` |
| `--red` | `#ef5350` |
| `--orange` | `#ffb74d` |
| `--font` | `Consolas, Monaco, Courier New, monospace` |
| `--tap-target` | `44px` |

---

## 4. 各页面要点

### Login
- 独立页面，不继承 base
- 居中卡片 max 400px，深色背景
- `user-scalable=no` 防缩放

### Dashboard
- 顶部三列统计（Nodes / Subs / Processes）
- 服务卡片可展开收起，展开后显示操作按钮
- CRUD 底部 sheet modal
- 定时 10s 刷新

### Inbounds
- 协议标签卡片（http/socks/ss/vmess）
- 编辑时动态切换表单字段
- 无自动刷新

### Outbounds
- single/direct 简单卡片
- auto switch 可折叠卡片 + 节点池列表
- 节点池内支持切换、排序、移除、延迟检测
- 节点选择 modal 支持过滤搜索

### 全局 JS 内置
- `showToast(msg, level)`：替代桌面 `addLog()`
- `showConfirm / showMessage / closeModal`：modal 控制
- `AppCache / cachedFetch`：API 数据缓存
---

## 5. 路由修改

`app/routes/pages.py` 新增 `_render_page(name, desktop_tmpl)` 分发函数，仅影响 dashboard / inbounds / outbounds 三个路由 + login。其余路由不变。

---

## 6. 兼容性
- iOS Safari 15.4+, Android Chrome latest
- 桌面端零影响

## 7. 验证项
- Chrome DevTools 设备模拟
- `?mobile=0/1` 参数切换
- 三个页面 CRUD + 展开/折叠
- 44px 触控区域
- Toast 通知
