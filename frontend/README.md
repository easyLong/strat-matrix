# Vue 前端子项目

已按驻场要求适配：`vue: ^2.6.14`（lock锁定2.6.14）、`vuex: 3.6.0`、`axios: 1.8.2`、`element-ui: 2.15.13`。Vue Router使用3.6.5，编译器与Vue统一为2.6.14；通过`npm ci`安装锁定依赖。宿主接入与验收边界见[Vue2迁入说明](VUE2_INTEGRATION.md)。

Node固定为**16.13.0**，实测npm **8.1.0**，允许npm 8；根目录及本目录`.nvmrc`、engines和生命周期检查防止误用其它Node。lock为npm8的v2格式。先通过行内提供的运行时切换方式激活对应版本，再执行以下命令；不要使用npm11重写锁文件。

三工程驻场适配详见[功能流程清单](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.md)及[Excel跟踪表](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.xlsx)。除菜单/请求/样式嵌入外，前1000候选筛选与UM导入的服务端能力需单独处理，不是仅替换API地址。

本目录独立安装、测试和构建，不需要Python环境或MySQL凭据。三个业务页面未来复制到客户现有前端工程。

```bash
npm ci
npm test
npm run build
npm run dev
```

Windows也可在仓库根目录使用`./scripts/frontend.ps1 version`、`./scripts/frontend.ps1 install`、`./scripts/frontend.ps1 test`、`./scripts/frontend.ps1 build`及`./scripts/frontend.ps1 dev`。脚本优先使用已激活的16.13.0，或本工作区忽略目录中的独立运行时；不下载软件、不修改系统Node，用完恢复当前进程PATH。

默认页面端口930。开发及preview的`/api/**`均代理到Java `http://127.0.0.1:6931/api/plan/**`，Java不可用时不会降级直连Python。`JAVA_GATEWAY_URL`可由启动器注入；行内`bank`模式必须明确提供该地址。静态构建不需要运行Java或Python。

浏览器继续使用相对`/api`路径。正式部署时客户网关／前端服务器也必须将该前缀映射到Java；Vite开发代理不是生产静态文件自带的代理。

页面请求集中在`src/api/`及`src/api.ts`，界面、路由和状态分别位于`src/views/`、`src/router.ts`和相关composables。迁入客户前端时复用客户的请求、身份、路由和UI基础设施。

现有组合逻辑通过`@vue/composition-api@1.7.2`在Vue2.6运行，组件均为普通`<script lang="ts">`，无需`script setup`或Vue3宏编译插件。独立页面启动使用`src/main.ts`；嵌入宿主时调用`installPlanningUi`、`attachPlanningStore`及`setPlanningHttp`，不要在宿主内再启动一个独立Vue应用。

共用接口约定见[三工程契约](../docs/contracts/README.md)。

当前版本验收及后续事项见[前端复核与修复](../docs/前端复核与修复_2026-11-04.md)：29项前端测试、20个浏览器场景及类型检查/构建通过。
