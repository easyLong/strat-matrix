# xiangliang供应商源码并入宿主

本地保留五个Maven模块供行外独立开发。行内直接合入已有`godp-digital-marketing`的五个模块，无需再创建一套Java应用或重复子模块。Java包、Spring Bean和Mapper资源按供应商隔离，目录定义集中在[布局契约](../contracts/vendor-layout.json)。五模块只使用公开库；真实行内BOM仍待现场验收。

统一Java根包为`com.pab.aitmp.aiis.godp.digital.marketing`，下表包路径均相对于此根包。

| 本地模块 | 行内已有模块 | 生产Java包落点 |
| --- | --- | --- |
| godp-planning-entity | godp-digital-marketing-entity | `entity.xiangliang` |
| godp-planning-api | godp-digital-marketing-api | `api.xiangliang` |
| godp-planning-client | godp-digital-marketing-client | `client.xiangliang` |
| godp-planning-services | godp-digital-marketing-services | `services.service.xiangliang`及`services.mapper.xiangliang` |
| godp-planning-server | godp-digital-marketing-server | `server.xiangliang`，排除`dev` |

## 导出源码

在仓库根目录执行，使用可用的Python 3.10以上版本：

```bash
python java-backend/tools/export_host_source.py --output run/exports/xiangliang-host-source.zip
```

工具按行内模块目录输出ZIP，包含生产Java、7份Mapper XML、未编译的接入代码模板、只读合并预检工具及SHA256清单。同一份源码导出得到相同的ZIP校验和。它不会覆盖同名ZIP，不修改宿主文件，不包含文档、本地POM、application配置、行外启动壳、测试夹具、运行数据或密钥。数据库发布包单独交DBA审核。

## 合并前只读预检

```bash
python java-backend/tools/inspect_host_source.py --package run/exports/xiangliang-host-source.zip --host-root "D:/work/godp-digital-marketing"
```

离线包解压后也可直接运行`integration-tools/xiangliang/inspect_host_source.py`，不依赖其他本项目文件或第三方Python包。`host-root`指包含五个`godp-digital-marketing-*`模块的目录。工具校验ZIP清单、文件校验和和供应商边界，然后输出JSON：

| 输出 | 含义与处理 |
| --- | --- |
| `new` | 宿主尚未存在的文件，按对应模块合并 |
| `identical` | 内容相同，可跳过 |
| `different` | 内容不同，逐项核对；特别保留现场已填写的SQL与适配修改 |
| `host_only_retained` | 宿主供应商目录独有文件，仅列出，不删除 |
| `missing_modules` | 所选目录中缺少的宿主模块，先核对合并根目录 |
| `manual_templates`、`delivery_tools` | 交付辅助文件，不复制到Java业务源码目录 |

退出码0表示检查通过且无差异待核对；2表示存在差异或缺少模块，须人工审阅；1表示包、路径或读取异常。工具不复制、不覆盖、不删除任何宿主文件。SHA256用于核对交付完整性，不替代供应商签名或行内发布审批。

## Mapper落点

```text
godp-digital-marketing-services/src/main/
  java/com/pab/aitmp/aiis/godp/digital/marketing/services/
    service/xiangliang/             业务服务及资料适配
    mapper/xiangliang/              7个Mapper接口
  resources/mapper/xiangliang/
    ManualMapper.xml
    BusinessPlanningConfigMapper.xml
    ConfigReleaseMapper.xml
    AutoScheduleMapper.xml
    PlanningQueryMapper.xml
    SlotCompletionMapper.xml
    source/BankSourceMapper.xml     待填写行内真实资料SQL
```

六份业务XML加载到同一业务库MyBatis会话，使用`classpath*:mapper/xiangliang/*Mapper.xml`。`SlotCompletionMapper.xml`引用`PlanningQueryMapper.xml`中的公共查询片段，两者必须加载到同一SqlSessionFactory；`BusinessMapperSupport.businessXml()`已统一返回六份业务XML。本地独立Slot装配与测试也已加载共享片段。资料SQL通过资料所属会话单独加载；不能默认资料库与策划业务库相同。若接已有Service，则实现`BankSourceQueries`，不加载此XML。所有XML namespace和实体类型引用均已与新包名一致。

也可在宿主现有MyBatis工厂初始化处调用`BusinessMapperSupport.appendBusinessXml(existingHostResources)`，追加本供应商六份XML并保留原资源；不要覆盖原Mapper列表或另建缺少权限插件的工厂。会话及事务别名参考[HostBusinessBindings.java.example](HostBusinessBindings.java.example)。

`PlanningHostConfiguration`启动时自动校验六个Mapper及其SQL语句是否齐全、执行器是否为SIMPLE/REUSE、是否使用Spring事务，以及标准JDBC事务管理器与会话是否同一DataSource。检查只读内存元数据，不连接数据库、不建表。自定义事务管理器若不暴露JDBC资源，只能完成映射检查并明确记录未验证，仍需宿主验证事务联动。

接入模板均在测试中以Java8编译验证，不自动参与生产装配。调度模板显式指定`xiangliangAutoScheduleHandler`等名称，不能只按`PlanningJobHandler`接口注入，因为共有四个实现。`inside`需追加到宿主已有环境配置，不应覆盖其现有Spring profiles。

## 行外准备

在java-backend执行：

```bash
mvn -Pdev verify
mvn -Pinside package
python tools/verify_s1_layout.py
```

dev供行外启动；inside生成普通server JAR，排除整个`server.xiangliang.dev`以及application配置，不打Boot可执行包装。它不替代宿主启动类。该profile跳过依赖开发夹具的测试编译；完整测试在dev构建中运行，其中inside装配验收显式关闭行外组件。不要覆盖运行中服务正在使用的JAR，应在独立目录构建。

## 驻场并入

1. 按导出ZIP的五个模块目录合并至行内已有模块，不再新建五个`godp-planning-*`子模块。
2. 使用宿主现有Parent，并由宿主管理Spring、MyBatis、Jackson、POI等版本。当前根POM只服务行外构建，不复制进宿主覆盖依赖管理。不要在没有effective POM的情况下假定内部BOM版本。
3. 保持依赖方向：api→entity，client→api，services→api/client，server→services/client；entity不得引用Service、Mapper或Controller。
4. 迁入services的Mapper、bank-source契约及业务DBA脚本。把六套Mapper绑定到宿主业务会话和同库事务管理器；不要由宿主组件扫描再注册一套不同数据源的Mapper代理。
5. 宿主server导入`server.xiangliang.config.PlanningHostConfiguration`，启用Spring inside与`planning.host.enabled=true`，按[装配说明](README.md)提供六类必需绑定和可选响应/上下文适配器。会话、事务、HTTP客户端分别使用`xiangliangBusinessSessions`、`xiangliangBusinessTransactions`、`xiangliangPythonHttp`别名；内部Bean统一带供应商前缀。
6. 数据源复用宿主；HikariCP、MySQL驱动、本地建表器、Fixture、LocalJobPulse均不迁入。导出工具排除`server/xiangliang/dev`，不能仅凭Spring profile假定它们不被打包。
7. 用宿主真实身份、资料SQL、数据范围和调度实现完成验收。inside库在行外编译通过不能证明这些能力已实现。

模块源码坐标统一为`com.pab.aitmp.aiis:godp-planning-*:0.1.0-SNAPSHOT`，现场如使用宿主统一groupId/version，集中调整POM和模块依赖；Java包名不需要跟着反复修改。不要手工将版本写进每个依赖，优先使用宿主dependencyManagement。

## 暂不迁移的内容

- `godp-planning-server/src/main/java/.../server/xiangliang/dev/**`及其application配置。
- 根旧target和各模块target下的开发产物，除非明确走已验收的制品交付。
- run、日志、数据库密码、模型Key、真实客户资料与现场私有SQL。

本轮保留现有HTTP路径、snake_case字段、HTTP状态码和业务SQL，无需因包路径迁移发布数据库DDL。强类型DTO、全POST、Excel与事务分页已另行收口。源码编译与隔离宿主验收不代表真实SSO、资料SQL、内部依赖和数据权限已经联调。
