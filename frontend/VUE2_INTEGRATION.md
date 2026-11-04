# Vue 2.6 驻场前端适配

日期：2026-11-04。三个业务页面保留原布局和流程，完成Vue3/Pinia到客户指定依赖的迁移。

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

执行前先激活Node16.13.0；版本由`.nvmrc`和package.json约束，错误版本会明确拒绝安装及运行脚本。实测npm8.1.0，锁文件格式2；测试改用支持Node16的Mocha10.8.2并按文件隔离，浏览器验收使用支持Node16的Playwright1.40.1（可选工具，不是生产依赖）。浏览器API和Node测试环境分别处理，测试辅助不会注入生产页面。

使用lock安装，避免Vue与编译器版本不一致。构建过程不访问数据库和模型。默认930端口，页面请求仍通过Java，开发/preview代理配置沿用`tooling/serverOptions.ts`；生产静态部署由宿主配置Java路径。

## 3. 迁入已有Vue2工程

复制src中的页面、业务组件、组合逻辑、类型、样式和工具；沿用客户的启动文件、菜单、Router、Vuex和构建配置。注册示例：

```ts
import Vue from 'vue'
import { installPlanningUi } from './strat-matrix/install'
import { attachPlanningStore } from './strat-matrix/store'
import { setPlanningHttp } from './strat-matrix/api/http'
import 'element-ui/lib/theme-chalk/index.css'

installPlanningUi(Vue)
attachPlanningStore(hostStore, 'stratMatrix')
setPlanningHttp(hostAxios)
```

- **状态**：`planningModule`为namespaced模块，`attachPlanningStore`只在不存在时注册，不覆盖宿主其它状态。模块名可指定，页面统一通过已有门面访问，无需逐页改Store调用。
- **请求**：默认Axios实例前缀`/api`、超时30秒；可以注入宿主Axios实例，其baseURL、会话和拦截器由宿主决定。注入实例需返回标准AxiosResponse，业务结果位于`response.data`；如果宿主客户端已直接返回业务体或增加统一包装，应集中在此边界适配，避免重复解包。
- **UI**：Element UI已经统一注册并加载主题；当前业务组件布局保留。宿主已有Element UI时，按宿主方案只加载一次主题，确认全局CSS与当前模块样式的作用范围。
- **路由**：默认`/config`、`/manual`、`/results`，旧`/auto`重定向到结果页。接入宿主菜单时确认路由前缀和返回路径。`compat/router.ts`集中提供响应式路由读取，兼容VueRouter3的导航取消/重复跳转。
- **构建**：当前源码为TypeScript，确认宿主TS/SFC loader支持该语法。模块内采用相对引用，复制到宿主src子目录时不依赖宿主`@/`别名。确保Vue只打包一份，版本为2.6.14。

不迁入行外node_modules、dist、临时转换工具或独立main.ts启动逻辑。此轮没有更改Java/Python协议、业务表或真实模型数据。

## 4. 验收

最新清理与修复记录见[前端复核](../docs/前端复核与修复_2026-11-04.md)：29项测试、20个浏览器场景通过，覆盖导出统一宿主Axios及中文显示修复。

原有21项业务测试已改用Vue2运行时/模板渲染；补充版本一致性、Axios请求/错误/取消/宿主注入、Vuex宿主模块和营销数量双向绑定测试。生产类型检查和构建通过。

隔离inside Java测试宿主使用H2和HTTP桩，已覆盖三个页面及详情的浏览器验收；不读取开发业务库，不调用真实模型。截图和报告保存在忽略目录`run/inside-host-browser/`，最终轮次结果见[迁移验收记录](../docs/前端Vue2驻场适配_2026-11-04.md)。

这是指定前端依赖和行外隔离接入的验证，真实宿主构建、SSO/数据权限、路由前缀、接口统一包装和样式共存仍需现场联调。

依赖兼容范围参考：[Vue官方Composition API插件](https://github.com/vuejs/composition-api)、[Vue2.6 Vite插件及版本约束](https://github.com/underfin/vite-plugin-vue2)。本项目已一次性移除setup宏，宿主无需增加对应宏转换插件。
