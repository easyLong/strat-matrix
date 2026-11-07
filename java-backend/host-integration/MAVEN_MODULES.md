# 五模块并入宿主

当前包名前缀已改为`com.pab.aitmp.aiis.godp.planning`，本地拆分不再依赖旧的`com.stratmatrix`源码。五模块只使用公开库；尚未验证真实Halo依赖。

## 行外准备

在java-backend执行：

```bash
mvn -Pdev verify
mvn -Pinside package
python tools/verify_s1_layout.py
```

dev供行外启动；inside生成普通server JAR，排除整个`server.dev`以及application配置，不打Boot可执行包装。它不是一个独立行内应用，不替代宿主启动类。该profile跳过本地测试编译，因为本地验收类依赖dev适配器；完整测试在dev构建中运行，其中inside装配验收显式关闭行外组件。

## 驻场并入

1. 对照实际宿主五层模块规则，注册`godp-planning-api/entity/client/services/server`。若宿主已有对应模块，可按包路径并入其现有模块，不额外创建另一套同名类。
2. 将模块Parent接到真实宿主Parent，并由宿主管理Spring、MyBatis、Jackson、POI等版本。当前根POM只服务行外构建，不直接复制进宿主以覆盖其依赖管理。不要在没有effective POM的情况下假定内部BOM版本。
3. 保持依赖方向：api→entity，client→api，services→api/client，server→services/client；entity不得引用Service、Mapper或Controller。
4. 迁入services的Mapper、bank-source契约及业务DBA脚本。把六套Mapper绑定到宿主业务会话和同库事务管理器；不要由宿主组件扫描再注册一套不同数据源的Mapper代理。
5. 宿主server导入`server.config.PlanningHostConfiguration`，启用Spring inside与`planning.host.enabled=true`，按[装配说明](README.md)提供六类必需绑定和可选响应/上下文适配器。
6. 数据源复用宿主；HikariCP、MySQL驱动、本地建表器、Fixture、LocalJobPulse和LegacyPageController均不迁入。迁源码时同样排除`server/dev`，不能仅凭Spring profile假定它们不被打包。
7. 用宿主真实身份、资料SQL、数据范围和调度实现完成验收。inside库在行外编译通过不能证明这些能力已实现。

模块源码坐标统一为`com.pab.aitmp.aiis:godp-planning-*:0.1.0-SNAPSHOT`，现场如使用宿主统一groupId/version，集中调整POM和模块依赖；Java包名不需要跟着反复修改。不要手工将版本写进每个依赖，优先使用宿主dependencyManagement。

## 暂不迁移的内容

- `godp-planning-server/src/main/java/.../server/dev/**`及其application配置。
- 根旧target和各模块target下的开发产物，除非明确走已验收的制品交付。
- run、日志、数据库密码、模型Key、真实客户资料与现场私有SQL。

S1保留了现有HTTP路径、snake_case字段、HTTP状态码和事务实现。强类型DTO、全POST、Excel与事务分页收口后续逐项推进；不应在现场无测试时一次性批量替换。
