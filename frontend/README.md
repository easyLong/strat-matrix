# Vue 前端子项目

本目录独立安装、测试和构建，不需要Python环境或MySQL凭据。三个业务页面未来复制到客户现有前端工程。

```bash
npm ci
npm test
npm run build
npm run dev
```

默认页面端口930。开发及preview的`/api/**`均代理到Java `http://127.0.0.1:6931/api/plan/**`，Java不可用时不会降级直连Python。`JAVA_GATEWAY_URL`可由启动器注入；行内`bank`模式必须明确提供该地址。静态构建不需要运行Java或Python。

浏览器继续使用相对`/api`路径。正式部署时客户网关／前端服务器也必须将该前缀映射到Java；Vite开发代理不是生产静态文件自带的代理。

页面请求集中在`src/api/`及`src/api.ts`，界面、路由和状态分别位于`src/views/`、`src/router.ts`和相关composables。迁入客户前端时复用客户的请求、身份、路由和UI基础设施。

共用接口约定见[三工程契约](../docs/contracts/README.md)。
