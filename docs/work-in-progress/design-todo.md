# ProxyHub 设计 TODO

本文记录需求确认后需要在模块设计阶段明确的实现事项。本文不是正式需求依据，设计结论不得改变 `docs/01-requirements.md` 规定的产品行为。

## sing-box 模块设计

### Outbound、Route 与 sing-box 配置映射

设计时需要明确并形成可验证样例：

- 全局 Node 到 sing-box 独立出站的字段映射、tag 生成和唯一性规则；
- 被 Route 引用的 MANUAL/AUTO 到 sing-box selector 的映射，以及未被 Route 引用的 MANUAL/AUTO 不生成 selector 的处理；
- Node Pool priority 到 selector 节点顺序的映射；
- MANUAL 持久化 Current Node 和 AUTO Fallback Node 到 selector 初始选择的映射；
- Current Node 切换后中断已有连接所需的 sing-box 字段及 Clash API 操作；
- DIRECT 对应的系统内置 direct outbound、保留 tag 以及 Route 到该 tag 的映射；
- Inbound、Route、selector、Node 独立出站和 DIRECT tag 的完整引用关系；
- sing-box cache file 是否启用，以及如何确保缓存的 selector 历史选择不会覆盖 MANUAL 持久化的 Current Node 或 AUTO 的 Fallback 初始化规则；
- 配置生成、`sing-box check`、正式配置原子替换及启动之间的执行顺序；
- 上述映射在仅有 DIRECT Route、MANUAL Route、AUTO Route、多条 Route 共享同一 Outbound，以及未被 Route 引用的 MANUAL/AUTO 等场景下的配置样例和验收方法。
