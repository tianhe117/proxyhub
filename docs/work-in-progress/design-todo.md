# ProxyHub 设计 TODO

本文记录需求确认后需要在模块设计阶段明确的实现事项。本文不是正式需求依据，设计结论不得改变 `docs/01-requirements.md` 规定的产品行为。

## sing-box 模块设计

### Outbound、Route 与 sing-box 配置映射

设计时需要明确并形成可验证样例：

- 全局 Node 到 sing-box 独立出站的字段映射、tag 生成和唯一性规则；
- 被 Route 引用的 MANUAL/AUTO 到 sing-box selector 的映射，以及未被 Route 引用的 MANUAL/AUTO 不生成 selector 的处理；
- Node Pool 到 selector 节点列表的映射和顺序规则，以及 AUTO 择优始终读取数据库 priority、不依赖 selector 顺序的实现方式；
- MANUAL/AUTO 的 Default Node 到 selector 初始选择的映射，以及 AUTO 将 Default Node 作为 Fallback Node 的处理；
- Current Node 的运行时切换、成功确认及中断已有连接所需的 sing-box 能力和调用方式；
- DIRECT 对应的系统内置 direct outbound、保留 tag 以及 Route 到该 tag 的映射；
- Inbound、Route、selector、Node 独立出站和 DIRECT tag 的完整引用关系；
- sing-box cache file 是否启用，以及如何确保缓存的 selector 历史选择不会恢复上一运行周期的 Current Node，或覆盖从 Default Node 初始化 Current Node 的规则；
- 配置生成、`sing-box check`、正式配置原子替换及启动之间的执行顺序；
- 上述映射在仅有 DIRECT Route、MANUAL Route、AUTO Route、多条 Route 共享同一 Outbound，以及未被 Route 引用的 MANUAL/AUTO 等场景下的配置样例和验收方法。

### Node 协议与输入映射

设计时需要明确并形成可验证样例：

- VMess、VLESS、Trojan、Shadowsocks 和 Hysteria2 的字段映射、合法组合及版本兼容范围；
- Reality、uTLS fingerprint、WebSocket、gRPC 和 HTTP/2 等能力适用的协议、字段组合和校验规则；
- 当前集成的 sing-box 可直接处理的 Shadowsocks plugin 范围、字段映射和校验方式，以及不安装或管理额外插件程序的实现边界；
- 单条分享 URI 的解析、字段回填和错误处理，以及必要字段、端口和协议参数的保存校验规则。

### 敏感信息处理

设计时需要明确：

- Node 凭据、分享 URI、完整 Subscription URL 和解析器原始输入等敏感信息的识别范围；
- 日志、错误信息和差异预览的统一脱敏位置及处理方式；
- 差异预览允许展示的安全字段和失败原因；
- HTTP、parser 和 sing-box 底层错误向用户展示或写入日志前的清理规则及验证样例。
