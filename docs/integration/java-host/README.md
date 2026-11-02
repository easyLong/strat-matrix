# 行内Java工程接入交接说明

**本目录是文档与交接参考，不是本项目的Java模块。所有Java实现最终写入行内现有工程。**

本仓库只开发和运行Vue与Python；不包含Java源码模块、Java构建、Java服务或JDK运行依赖。方法及字段模板以 `.java.example` 保存，供驻场时复制、改包名并按宿主规范实现。

Python保留策划业务和算法。Java部分的目标是让行内开发清楚需要补什么，不在行外提前绑定宿主的Spring、Servlet、HTTP客户端或调度框架。

## 1. 当前保留的内容

| 文件 | 作用 | 实现状态 |
| --- | --- | --- |
| `templates/PlanningGateway.java.example` | 一个通用转发方法及HTTP请求／响应对象 | 文档模板，无HTTP实现 |
| `templates/PendingPlanningGateway.java.example` | 转发方法占位参考 | 文档模板，方法抛出未实现异常 |
| `templates/BankDataReader.java.example` | 六类行内资料和状态查询方法 | 文档模板，无SQL |
| `templates/PendingBankDataReader.java.example` | 六类查询方法占位参考 | 文档模板，方法全部抛出未实现异常 |
| `templates/BankContracts.java.example` | 行内读取所需的查询条件和返回对象，含中文说明 | 字段参考，不访问数据库 |
| `contracts.json` | 读取契约的字段及约束参考 | 不代表实际表结构 |

模板使用JDK基础类型示意，不提前绑定Spring、Servlet或Maven。本项目不编译这些模板；未来行内实现也不能用空列表或固定成功冒充已接通。

## 2. 行内需要补的三件事

### 2.1 一个通用业务转发入口

在宿主已有Java工程中实现 `PlanningGateway.forward`，再按宿主框架接一个通配路由。无需逐个重写页面接口Controller和业务DTO。

建议路径映射（最终由宿主确认）：

| 前端访问 | Java转发到Python |
| --- | --- |
| `GET /api/plan/config` | `GET /api/config` |
| `POST /api/plan/query/accounts` | `POST /api/query/accounts` |
| `POST /api/plan/items/123/replace-topic` | `POST /api/items/123/replace-topic` |
| `POST /api/plan/query/export` | `POST /api/query/export` |
| `/api/plan/integrations/bank/op...` | `/api/integrations/bank/op...` |

行内实现步骤：

```text
接收请求
→ 从真实登录态或服务认证取得身份
→ 校验当前方法、路径对应的授权及数据范围
→ 将固定公共前缀替换为Python的/api前缀
→ 注入可信操作人与服务调用身份
→ 使用宿主已有HTTP客户端同步转发
→ 保留Python状态码、正文和必要响应头
```

建议随方法注释补齐的要求：

- Python目标服务地址固定由宿主配置，不能从浏览器参数取得。
- 保留原始编码、重复查询参数、JSON及二进制正文；不重复解析业务DTO。
- 当前Python服务凭据为 `X-Integration-Token`，操作人字段为 `X-Operator-Id`；最终可按双方约定调整。不能把浏览器填写的UM当作可信身份。
- 页面使用会话身份，OP使用服务身份；权限在宿主控制。接口契约、路径及授权目录仍需维护。
- 普通业务通配入口不得开放Python内部唤醒、模型管理、任务控制及IF查询占位入口。
- Python的201、202、409、422、5xx等状态与错误正文保持准确，不统一包装成200。
- 下载保留内容类型、文件名和字节内容。`PlanningGateway`中的字节对象是有界响应示意；大文件应在宿主实现时使用流式承接，不能强制整体读入内存。
- 请求头不能全量照搬；身份凭据、逐跳头、连接信息和错误响应按宿主代理规范处理。
- 连接／读取超时、连接池、并发限制、文件传输预算及异常映射使用宿主规范，不在本目录提前实现一套。

当前页面主流程涉及25种请求，OP-01～04另有4个入口。接口定义在Python和前端API层保留，不需要在Java逐个实现同名业务方法。OP-04实际调用模型，不属于毫秒级纯查询；本轮不改变其执行方式或编号。

### 2.2 一个宿主调度唤醒调用

按宿主已有调度框架增加一个Job Handler，调用拟定的 `POST /api/internal/wakeup`。Java不判断周策划、热点T-1或策划重试逻辑。

本目录仅记录该接点，不创建Job实现或定时器。Python唤醒入口及常驻受控执行器仍按架构备忘后续改造，不代表已经存在。

脉冲间隔暂以五分钟讨论，实际可配置；受理成功与业务完成分别监控。任务查询为必要能力，回调按宿主需要选择。

### 2.3 六类行内查询方法

| 预留方法 | 行内需要填充的对象 |
| --- | --- |
| `accounts` | 账号、人设、兴趣、性别、表达风格、粉丝量及互动事实 |
| `topics` | 普通／热点来源，营销／非营销类型，标题、大纲、二级分类和有效期等 |
| `marketingContents` | 账号可用的过审营销内容，按先过审优先 |
| `effectiveMarketing` | 账号目标日期已有的有效营销投放 |
| `productionResults` | 策划明细对应版本的内容状态、内容ID、更新时间和失败原因 |
| `marketingResults` | 人工营销生产进度；后续账号、内容及审核明细契约仍需补齐 |

由策划侧先定义对象，行内提供表结构，驻场共同补SQL和字段映射。Python通过Java接口读取，不直查行内业务库。

## 3. 前端和部署预留

Vue保持相对 `/api` 请求。现有Vite行内模式把 `/api/...` 映射到Java的 `/api/plan/...`；Nginx示例保留同样的建议映射。**这是未来接入路径，不代表Java已经实现。** 实际前缀不同时再统一调整。

`JAVA_ACCESS_MODE=bank` 时必须配置实际Java入口，不能因Java尚未实现而悄悄回退直连Python。本地开发模式继续使用独立Python，不受Java占位影响。

## 4. 验证与交接边界

- 校验方法、字段、占位边界等交接资料完整，不在本项目的后端测试中启动Java或调用JDK。
- 校验交接包只在文档目录携带Java参考模板和字段Schema，不包含Java源码模块、Spring/Maven实现、Controller、HTTP转发器或编译产物。
- 前端测试覆盖行内预留路径和本地开发路径。
- 真实转发、登录、权限、SQL、调度和内容生产需驻场实现与联调，不能把先前模拟转发测试当作当前Java已实现或行内已验收。

目标架构见 [V0.1改造备忘](../../行内整合架构改造备忘_V0.1.md)；工程归属修订见 [V0.2备忘](../../行内整合架构改造备忘_V0.2.md)。V0.1保留作为原始讨论基线。
