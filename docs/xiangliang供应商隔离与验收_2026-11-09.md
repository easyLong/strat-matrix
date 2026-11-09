# xiangliang供应商隔离与验收

日期：2026-11-09。本轮按行内已有五模块和供应商目录要求迁移Java代码，保留行外独立构建。业务服务放入`services/service/xiangliang`，Mapper接口放入`services/mapper/xiangliang`；其他四层均使用各层独立`xiangliang`包。完整落点见[并入宿主](../java-backend/host-integration/MAVEN_MODULES.md)。

本文汇总供应商目录迁移及后续接入优化，以下为最终交付与验收口径。提交分支为`feature/planning-v2`；行内工程继续复用其已有五模块、父POM及启动类。

## 已完成

- 167个原主源码文件按新包移动，并新增`BusinessMapperSupport`，当前共168个主源码文件。同步更新测试、引用、OGNL类型名、XML namespace、组件扫描、启动主类和inside排除规则；旧源码不保留兼容副本。
- 六份业务XML放入`mapper/xiangliang/`，资料XML放入`mapper/xiangliang/source/`，分别绑定业务与资料所属会话。
- 内部Bean统一使用`xiangliang`前缀，防止宿主同名组件覆盖。事务边界服务与事务管理器分别命名；异常Advice限定本供应商server范围。
- 新增[布局契约](../java-backend/contracts/vendor-layout.json)和[源码导出工具](../java-backend/tools/export_host_source.py)，按已有`godp-digital-marketing-*`目录输出ZIP，不携带POM、开发启动壳、文档或私有配置；包含源码SHA256清单。
- 更新宿主装配、资料查询模板、目录和制品检查。HTTP接口、14张业务表、3个视图、13份权威SQL以及V19算法保持原契约。
- 启动时检查六个业务Mapper及SQL映射、执行器、Spring事务工厂和标准JDBC同库资源，不连接数据库；自定义事务管理器无法从公开接口判定同库时，明确记录需宿主验证。
- 补齐六份宿主接入模板并以Java8编译验收；调度Handler按名称注入，inside示例不覆盖宿主已有profiles。
- 新增只读合并预检，区分新增、相同、差异及宿主独有文件，不自动覆盖现场SQL或其他供应商代码。源码ZIP可复现，携带独立预检脚本；SHA256仅用于完整性核对。
- 同步README、当前状态、宿主说明及驻场清单Markdown/CSV/Excel的代码路径，修正失效的前端导航链接。

## 验证

为避免覆盖运行中的Java JAR，本轮在忽略目录`.tmp-xiangliang-optimization-java`复制源码后独立构建；目录迁移首轮证据仍保留在`.tmp-xiangliang-java`。

| 检查 | 结果 |
| --- | --- |
| Java完整回归 | 152项：147通过、5项真实外部环境验收按原设置跳过 |
| 同宿主其他供应商Bean | 原有常用Bean名保留，xiangliang组件独立装配，声明式事务回滚有效 |
| 同名Mapper文件和statement | 两个`ManualMapper.xml`和`ping`可同时加载，以完整namespace区分 |
| 隔离inside宿主三页面 | 53种浏览器状态通过；覆盖配置、人工、营销、导出、结果、换题及多宽度 |
| dev及inside制品 | Java8字节码通过；inside不含dev启动壳、application配置及旧namespace |
| Python与测试工具 | 527项及149子测试通过；工具53项通过，含10项导出/合并检查 |
| 宿主接入模板 | 六份模板Java8编译通过；未引入真实私有SDK |
| 启动期持久化检查 | 缺SQL、绑定错库、BATCH及非Spring事务工厂均拒绝；检查不建立数据库连接 |
| 离线合并预检 | 现场SQL/私有文件保留、其他供应商隔离、越界拒绝、包校验及可复现导出通过 |
| 独立预检脚本 | 从ZIP取出后在项目外、隔离Python路径下运行通过，无宿主文件写入 |
| V19固定回放 | 5账号、60选题、15条策划，与原基线一致 |
| API和SQL契约 | 6个Controller、14表、3视图、13份SQL校验通过 |

完整日志及浏览器截图位于忽略的`run/xiangliang-*`、`run/regression/xiangliang-*`、`run/inside-host-browser/`。浏览器报告中的故障场景用于验证异常提示，不代表真实内容系统已接通。

## 现场仍需处理

1. 源码合入宿主既有模块，使用真实Parent/BOM及现有依赖版本。
2. 为模块提供宿主会话、同库事务管理器及受控HTTP客户端的供应商别名；避免同时重复MapperScan注册。
3. 填写真实资料SQL或已有Service方法、字段和状态映射。当前`BankSourceMapper.xml`仍为明确报错的占位，不是行内表结构实现。
4. 接入真实身份、数据权限、配置来源、调度与内容流水写入端口，按宿主发布流程验收。

本轮不修改数据库，不重启或覆盖现有运行服务，不调用公网模型。新包名需部署新构建产物后才用于运行实例。

## 使用入口

- [宿主模块落点、导出和只读合并检查](../java-backend/host-integration/MAVEN_MODULES.md)。
- [必需Bean、权限和调度装配](../java-backend/host-integration/README.md)。
- [真实资料查询契约和现场字段映射](../java-backend/host-integration/BANK_SOURCE_CONTRACT.md)。

源码ZIP在`run/exports`生成，该目录不提交Git。GitHub保存源码、模板、导出及预检工具，可按上述命令重新生成交付包。
