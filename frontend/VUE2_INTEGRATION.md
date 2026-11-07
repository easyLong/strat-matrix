# Vue 2.6 驻场前端适配

更新日期：2026-11-07。三个业务页面保留原布局和流程，完成Vue3/Pinia到客户指定依赖的迁移，并新增统一宿主接入口、路由/权限适配、样式隔离与缓存生命周期处理。

后续已按现场要求完成Node **16.13.0**／npm **8.1.0**实际安装、测试、构建及浏览器验收，见[Node16验收记录](../docs/前端Node16适配_2026-11-04.md)。

## 1. 运行依赖

| 依赖 | package.json | 实际锁定版本 |
| --- | --- | --- |
| Vue | `^2.6.14` | 2.6.14 |
| Vuex | `3.6.0` | 3.6.0 |
| Axios | `1.8.2` | 1.8.2 |
| Element UI | `2.15.13` | 2.15.13 |
| Vue Router | `3.6.5` | 3.6.5 |
| Composition API | `1.7.2` | 1.7.2 |

`@vue/composition-api`用于复用已有画像配置、筛选、分页、异步请求及详情逻辑，必须在页面创建前注册。普通Vue2 SFC通过`defineComponent/setup`组织逻辑；没有Vue3运行时、Pinia、`defineModel`、`script setup`或Teleport依赖。多根模板已处理为Vue2单根，弹层通过可销毁的BodyPortal挂到body。

`vue-template-compiler`和测试用`vue-server-renderer`均锁定2.6.14。行外使用支持Vue2.6的`vite-plugin-vue2@2.0.3`和Vite4.5.14；Vite及测试渲染器不需要迁入宿主的生产运行依赖。

## 2. 独立安装与启动

在frontend目录执行：

```bash
npm ci
npm test
npm run build
npm run dev
```

执行前先激活Node16.13.0；版本由`.nvmrc`、`.node-version`和package.json约束，错误版本会明确拒绝安装及运行脚本。实测npm8.1.0，锁文件格式2；测试改用支持Node16的Mocha10.8.2并按文件隔离，浏览器验收使用支持Node16的Playwright1.40.1（可选工具，不是生产依赖）。浏览器API和Node测试环境分别处理，测试辅助不会注入生产页面。

使用lock安装，避免Vue与编译器版本不一致。构建过程不访问数据库和模型。默认930端口，页面请求仍通过Java，开发/preview代理配置沿用`tooling/serverOptions.ts`；生产静态部署由宿主配置Java路径。

## 3. 迁入已有Vue2工程

迁入`src/{host,views,components,composables,compat,ui,api,styles,data}`及`integration.ts`、`integration.css`、`App.vue`、`api.ts`、`store.ts`、`types.ts`、`style.css`、时间/标签工具。沿用客户启动文件、菜单、Router、Vuex和构建配置。统一注册示例（路径和宿主对象为示意，以实际宿主为准）：

```ts
import { createPlanningIntegration, PlanningRequestError } from './strat-matrix/integration'
import './strat-matrix/integration.css'

const planning = createPlanningIntegration({
  http: hostAxios,                 // 现有请求客户端，保留宿主登录态和拦截器
  store: hostStore,                // 现有Vuex，注册stratMatrix命名空间
  routePrefix: '/operations/strat-matrix',
  apiPrefix: '/godp/api/plan',      // 完整同源Java路径，确认上下文后只在此处修改
  can: capability => hostAccess.can(capability), // 在此将模块能力映射到已登记的行内权限码
  responseMode: 'axios',           // 标准AxiosResponse；已返回业务体的客户端改为body
  // 宿主有统一业务包装时显式配置，不猜测成功码或data层级：
  // unwrapResponse: body => {
  //   if (body.code !== HOST_SUCCESS_CODE) throw new PlanningRequestError(body.message, 422)
  //   return body.data
  // },
  // readError: error => hostErrors.message(error),
  // onRequestError: error => hostErrors.handle(error.status, error.message, error.retryAfter),
})
planning.routes.forEach(route => hostRouter.addRoute(route))
```

`createPlanningIntegration`在挂载前调用一次，不创建另一个Vue应用或VueRouter。宿主模式必须提供HTTP、Vuex、路由前缀、Java接口前缀和同步权限判断；缺少这些配置明确报错。导入HTTP模块不会新建Axios实例，本地默认实例仅在行外请求发生时创建。返回的父路由使用`PlanningHostView`，不显示本项目独立侧栏、顶部栏或页签；三个业务页使用宿主提供的独立可关闭页签，不显示面包屑。宿主已有Element UI时默认不重复注册或加载主题，Composition API和BodyPortal统一安装。

- **状态**：`planningModule`为namespaced模块，`attachPlanningStore`只在不存在时注册，不覆盖宿主其它状态。模块名可指定，页面统一通过已有门面访问，无需逐页改Store调用。
- **请求**：行外懒加载默认Axios前缀`/api`、超时30秒；宿主复用现有客户端，使用显式`apiPrefix`。支持`axios`和`body`返回模式，可集中设置`unwrapResponse/readError/onRequestError`。下载不经过业务解包，保留Blob；标准Axios模式保留响应头，body模式只能保留Blob自身类型。错误保留HTTP状态和429的有界重试秒数，不在页面自动循环重试。401登录跳转、统一提示及错误码由宿主回调处理。
- **UI**：`integration.css`将共享选择器限定在`.planning-ui`内，变量不写入宿主`:root`；BodyPortal自带同一作用域，停用时隐藏。App的DOM增强只观察模块根节点；滚动、键盘监听、ResizeObserver和轮询停用后清理，激活后恢复。`styles/standalone.css`仅供行外启动，不能复制到宿主公共样式。真实宿主浏览器需确认CSS变量、`:where`和现有页面API支持。
- **路由**：独立模式仍为`/config`、`/manual`、`/results`；宿主通过返回的命名路由`stratMatrix.config/manual/results`和显式前缀注册。`compat/router.ts`将现有导航、RouterLink集中映射，保留query/hash和返回分页信息，不重复添加前缀、不改宿主其它页面路径。宿主Router原有全局鉴权继续生效，模块入口另做能力检查。路由元数据提供`closable:true`、`keepAlive:true`和稳定的`tabKey`（业务根路径），现场映射到宿主页签协议；账号/周期/批次参数不创建新的一级页签。宿主负责页签关闭、缓存移除和未保存修改的关闭拦截，不能把路由标记当作已经实现的宿主页签管理器。
- **构建**：当前源码为TypeScript，确认宿主TS/SFC loader支持该语法。模块内采用相对引用，复制到宿主src子目录时不依赖宿主`@/`别名。确保Vue只打包一份，版本为2.6.14。

不迁入行外`main.ts`、`router.ts`、`index.html`、`node_modules`、`dist`、Vite配置、`styles/standalone.css`和测试宿主。沿用宿主Node16/内部registry/lock/代理配置，不复制行外公开registry地址，不新增SSO、网关或独立登录页。本轮没有更改Java/Python接口协议、业务表或真实模型数据。

### 权限与菜单登记

| 模块能力 | 对应操作 |
| --- | --- |
| `config.view` | 配置页面、配置历史查看 |
| `config.edit` | 编辑、保存及标签修改 |
| `config.restore` | 恢复历史版本 |
| `manual.view` | 人工策划任务列表 |
| `manual.create` | 新建、选择及提交人工策划 |
| `results.view` | 账号/时间列表、策划详情 |
| `results.export` | 报表、失败UM明细导出 |
| `results.replace` | 查看候选并替换选题 |

这些名称是模块内部能力，不是已申请的行内权限码。现场集中完成能力映射及菜单/按钮登记；`meta.planningPermission`供宿主路由登记使用。前端同时控制入口和发请求前检查，不能替代Java鉴权和SQL数据范围。人工/结果页面初始化需要读取共享当前配置，历史查看及修改仍使用各自能力；真实接口授权由Java按业务需要落实。未知权限不应默认返回true。

### 缓存与宿主边界

支持普通路由及宿主`keep-alive`。离开后停止配置同步、任务/内容轮询、日期检查和页面监听；弹层隐藏，返回恢复，分页状态保留。确认放弃配置修改后清理草稿，避免缓存再次显示已放弃内容。Vue2的缓存祖先判定集中在`useActivePage`，防止页面停用后刚挂载的子组件重新绑定监听。

现场仍需提供实际菜单/权限编码、Axios包装和错误处理、前后端路径、宿主TS/SFC loader、内部npm可用依赖以及样式/弹层层级约定。当前源码使用TypeScript，不能仅按截图的`api/xxx.js`示例假定不需要TS支持。

## 4. 验收

当前48项前端测试通过；另有真实Vue2 Router/Vuex/Axios的模拟宿主浏览器验收，覆盖三页面、带前缀跳转/返回、响应包装、页面和按钮权限、样式隔离、缓存弹层、轮询及监听清理，无数据库或模型调用。测试入口：

```bash
npm test
npm run build
node node_modules/vite/bin/vite.js build --config tests/host/vite.config.ts
# 仅在已安装Playwright和Chrome的测试环境执行，可用环境变量指定既有安装路径：
node tests/host-integration.browser.cjs
```

测试宿主代码在`tests/host/`，产物和报告位于忽略目录`run/frontend-host-preview`、`run/frontend-host-acceptance`。Java隔离宿主53个浏览器状态通过，含105标签、60选题的密集资料、独立页签关闭与长标题气泡；证据在`run/inside-host-browser`。这些结果不代替真实宿主Webpack构建、权限SDK、网络及数据范围联调。

历史清理与修复记录见[前端复核](../docs/前端复核与修复_2026-11-04.md)：当时29项测试、20个浏览器场景通过，覆盖导出统一宿主Axios及中文显示修复。

原有21项业务测试已改用Vue2运行时/模板渲染；补充版本一致性、Axios请求/错误/取消/宿主注入、Vuex宿主模块和营销数量双向绑定测试。生产类型检查和构建通过。

隔离inside Java测试宿主使用H2和HTTP桩，已覆盖三个页面及详情的浏览器验收；不读取开发业务库，不调用真实模型。截图和报告保存在忽略目录`run/inside-host-browser/`，最终轮次结果见[迁移验收记录](../docs/前端Vue2驻场适配_2026-11-04.md)。

这是指定前端依赖和行外隔离接入的验证，真实宿主构建、SSO/数据权限、路由前缀、接口统一包装和样式共存仍需现场联调。

依赖兼容范围参考：[Vue官方Composition API插件](https://github.com/vuejs/composition-api)、[Vue2.6 Vite插件及版本约束](https://github.com/underfin/vite-plugin-vue2)。本项目已一次性移除setup宏，宿主无需增加对应宏转换插件。
