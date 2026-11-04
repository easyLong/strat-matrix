# 请求上下文、响应适配与资料分页

版本：V0.1，2026-11-03。适用于现有宿主装配，不新增私有SDK、数据库表或调度器。原有六类必需绑定继续保留；增加的`HostContextProvider`和`PlanningResponseAdapter`均为可选宿主扩展。

## 1. 请求上下文：集中接一次可信身份

```text
宿主登录/功能授权 HostAccess
  → HostContextProvider读取可信会话
  → PlanningRequestContext（UM、机构范围、追踪号）
  → 页面Controller / Service / 资料读取
  → 请求完成或切入异步处理时清理
```

`HostAccess.authorize`仍负责认证与操作授权。通过后调用可选的`HostContextProvider.resolve`，将宿主已有身份对象转换为模块对象。未提供Provider时，使用原有`ManualPorts.Actor`的可信UM，机构范围为`UNSPECIFIED`，生成追踪号；这是兼容身份接入，**不是默认全机构权限**。

现场可在宿主配置中注册：

```java
@Bean
HostContextProvider planningContextProvider() {
    return request -> {
        // 以下currentUser为宿主可信会话对象的示意，按实际SDK取得，不取浏览器自报头。
        return new PlanningRequestContext(
            currentUser.um(),
            PlanningRequestContext.Scope.ORGANIZATIONS,
            currentUser.authorizedOrganizationCodes(),
            currentUser.trustedTraceId()); // 无追踪号时传null，自动生成
    };
}
```

示例不作为真实行内SDK实现，不自动编译。UM、机构范围和traceId不能直接相信浏览器传入的`X-User-UM`、`X-Operator-Id`、机构筛选或`X-Request-Id`；可信网关透传值也应经过宿主认可的来源校验。

| Scope | 含义 | 接入要求 |
| --- | --- | --- |
| `UNSPECIFIED` | 旧Actor只提供了身份，未声明结构化范围 | 继续由宿主已有权限机制执行，不能解释为ALL |
| `NONE` | 明确无数据范围 | SQL/Service不能返回无权数据 |
| `ORGANIZATIONS` | 明确授权机构集合 | 集合必须非空，SQL/Service应用范围；不可从页面筛选反推权限 |
| `ALL` | 宿主明确授予全范围 | 必须显式选择；不携带机构集合 |

`PlanningRequestContext`及机构集合不可变。使用`RequestContexts.require()`读取；无上下文会明确报错。`RequestContexts.current()`用于确实允许无页面身份的代码。账号、人设、内容等SourceFacts查询及业务Mapper仍需落实范围条件，不能仅把上下文对象作为“权限已完成”的依据。

普通人工、营销任务、换题、配置及标签保存已通过`RequestContexts.actor`优先使用请求中的可信UM。无请求上下文的测试、outside和宿主后台任务使用原先显式注入的Actor；业务任务执行仍沿用持久化发起人。不要把Actor本身实现为“必须读取RequestContexts”，再让默认Provider反向调用它，这会产生初始化循环；这种接法应同时提供HostContextProvider。

内部资料HTTP继续独立验证服务令牌，不经过员工Provider，也不继承浏览器身份。机器任务的原始数据权限由宿主按服务身份确定，不能因上下文为空而自动授予全范围。

上下文采用普通ThreadLocal，不自动传播到线程池；Servlet异步切换时立即清理，并在回派请求时重新建立。重任务依靠持久化任务数据执行，不持有整份员工请求上下文。若宿主新增异步页面计算，需要明确传递必要的不可变身份信息并在目标线程限定作用域，不能依赖默认继承。

页面成功及错误响应使用`X-Request-Id`返回追踪号；现有PythonClient在有上下文时把同一追踪号发往Python，不透传机构权限集合。日志MDC和行内链路追踪SDK仍由宿主装配，此处不自行实现一套追踪系统。

## 2. 异常与响应：集中接一次宿主格式

`PlanningApiErrors`已集中处理原Controller中的业务、配置冲突、输入校验、数据库/算法不可用及未知异常；Controller不再重复声明异常处理方法。

默认继续采用HTTP状态及`{"detail":"提示"}`；正常页面JSON结构不包装。已明确标记的配置校验仍显示原中文提示；普通IllegalArgumentException和未知异常使用通用提示，避免直接输出私有SQL、连接或内部堆栈。

| 错误类别 | 默认状态 | 内部错误码 |
| --- | --- | --- |
| 已定义业务异常 | 沿用业务状态 | `BUSINESS_ERROR` |
| 配置版本/初始化冲突 | 沿用配置状态 | `CONFIG_CONFLICT` |
| 必填及业务输入校验 | 422 | `VALIDATION_ERROR` |
| 参数类型、JSON、缺少参数等 | 422 | `INVALID_ARGUMENT` |
| 数据库不可用 | 503 | `DATABASE_UNAVAILABLE` |
| 计算服务连接/服务端故障 | 503 | `UPSTREAM_UNAVAILABLE` |
| 计算服务明确拒绝请求 | 沿用4xx | `UPSTREAM_REJECTED` |
| 请求方法/媒体类型不支持 | 405 / 415 | `METHOD_NOT_ALLOWED` / `UNSUPPORTED_MEDIA_TYPE` |
| 未分类异常 | 500 | `INTERNAL_ERROR` |

错误码目前提供给可选适配器，默认不会额外加入前端现有响应体。页面若要求行内统一格式，只注册一个`PlanningResponseAdapter`，例如：

```java
@Bean
PlanningResponseAdapter planningResponses() {
    return new PlanningResponseAdapter() {
        public Object success(Object body) {
            return Json.map("code", "OK", "data", body);
        }
        public ResponseEntity<?> error(Failure failure) {
            return ResponseEntity.status(failure.status).body(Json.map(
                "code", failure.code, "message", failure.message,
                "trace_id", failure.traceId));
        }
    };
}
```

上例只是公开格式示意，实际返回宿主标准对象即可。保持HTTP错误语义，配合Vue统一请求封装处理宿主包装；不能只在Java启用包装却不调整前端的拆包规则。当前没有启用此包装，因此现有页面无需改动。

成功响应适配只覆盖模块的正式页面Controller及JSON成功体。CSV/XLSX字节、Resource、流、字符串和非成功响应不套成功壳；导出文件名及媒体类型保持原样。错误包装不再被当成成功体二次包装。

`SourceFactsController`供Python使用的内部资料响应固定保留原始数据与`detail`错误契约，**即使页面启用宿主包装也不变**。这是为了避免每次修改行内页面格式都要修改算法取数。宿主其他模块及旧代理不参与本模块的成功包装。

迁入时一起导入`PlanningApiErrors`和`PlanningApiResponseAdvice`，`PlanningHostConfiguration`已包含。纯MockMvc standalone测试也要显式设置这两个Advice。宿主已有全局异常/响应Advice时，需确认扫描范围和优先级，避免同时重复包装；本模块不替代宿主全部工程的异常规范。

## 3. 资料分页：统一读取与边界检查

`SourcePageReader`供`SourceCatalogAdapter`、`ContentFactsAdapter`共用，查询入口仍是原`SourceFacts`，不新增HTTP接口或原始资料表。

| 方法 | 用途 | 是否允许按数量截取 |
| --- | --- | --- |
| `first(capability, filters, limit)` | 页面候选等原有有上限查询 | 明确只取前N条；不会把它称为全量 |
| `all(capability, filters)` | 热点、可引用营销内容等需要完整集合的查询 | 超过预算报503，不返回部分集合冒充完整 |
| `byIds(capability, ids, limit)` | 账号/选题定向查询 | ID先去重，每批≤500，所有批次共享请求预算 |

默认每页500、最多100次资料请求，预算在一次读取调用内生效；账号/选题ID输入最多50000条。显式空ID列表不查询，null表示未限定。现有人工页面及冻结输入的1000条来源上限继续保留，未改变候选选取业务规则。

读取器检查：分页对象、列表及记录类型、整数total、页码及每页回显、总数与条数一致、业务ID、跨页/跨批重复、请求ID范围、营销账号归属。支持既有中文返回别名，但字段中英文同时出现且冲突会报错。

- total在读取期间变化：409，要求调用方重新查询；不把前后两份资料拼成成功结果。
- 空页但total仍有剩余、重复ID、错误页码、缺少业务ID等：502。
- 完整读取或多批ID查询超过预算：503。不会在方法内部无限循环或自动发起重试。

OFFSET分页仍不能证明底层资料是同一数据库快照；固定更新时间上界及源库一致性由宿主实现。这里会检测部分不一致，不宣称解决全部并发变化。

营销过审分配先收集全部账号ID、去重并批量读取，再按原内容顺序组装账号快照；不再每条内容调用一次账号查询。账号缺失仍明确失败，不伪造快照。每次SourceFacts查询内部如何使用MyBatis及权限不变。

## 4. 验证与现场替换范围

定向测试：

```bash
# java-backend目录
mvn test -Dtest=HostRequestContextTest,PlanningApiBoundaryTest,SourcePageReaderTest,ContentFactsPagingTest,PythonClientTest,InsideThreePagesAcceptanceTest

# 仓库根目录：完整离线回归
python -m testing
```

测试覆盖可信身份、清理及异步切换、上下文不继承、业务UM优先级、Python追踪号、默认/宿主包装、内部契约隔离、二进制下载、参数与故障、分页范围/重复/变化/预算，以及三页面真实模块装配。使用H2、合成资料和HTTP响应桩；不接入行内真实身份或数据库。

驻场继续只替换宿主身份/范围读取、响应格式适配、原始SQL/Service及必要的宿主SDK装配。公共业务Service、资料分页和Python协议可继续复用；实际权限SQL、SSO、日志追踪和数据库性能仍须现场验收。
