# 需求冻结后待设计事项

ProxyHub V1.0 需求已全文冻结。本文仅记录需求确定了业务边界、但仍需在设计阶段明确的配置生效、页面展示和内部 API 细节；不增加或修改正式需求。后续可将这些事项合并到设计 TODO。

## 1. Settings 逐项生效时机

* 为每个 Setting 明确生效时机，并与管理保存限制、直接修改配置文件的生效规则保持一致。
* 明确检测参数和 AUTO 控制参数在下一次 sing-box Start 时如何初始化，以及一次检测或控制周期使用的参数版本。
* 明确 Settings 保存与 Start 并发时，如何保证 Start 使用开始时已成功保存的设置。

## 2. Node Pool 与节点角色展示

* 明确 Node Pool 按 priority 展示和调整的方式，以及相关内部 API 的数据表达。
* 明确 MANUAL 的 Current Node 与 Default Node 如何分别展示；未被 Route 引用的 MANUAL 不展示运行中的 Current Node，其节点选择仅更新 Default Node。
* 明确 AUTO 的 Current Node、Fallback Node 和 Candidate Node 如何区分展示。
* 明确 Node 健康状态及最近一次检测信息在页面和内部 API 中的展示字段。

## 3. 检测进行中的状态

* 明确单 Node 和批量人工检测尚未完成时的页面状态及内部 API 返回方式。

## 4. 运行信息不可获取时的表达

* 明确 Current Node 或 sing-box 实际进程状态不可获取时，页面和内部 API 如何表达；区分未运行、未被 Route 引用和查询失败。

## 5. 禁止操作的反馈

* 明确管理状态或实际进程状态不满足操作条件时，页面提示和内部 API 的失败返回；覆盖配置修改、MANUAL 切换、人工检测及运行控制操作。
