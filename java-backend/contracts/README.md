# S0兼容基线

`s0-baseline.json`来自重构前已发布的`e8ec62f`。它记录6个正式Controller的Mapping/状态码声明、3个输入对象的公开字段、14张业务表、3个视图及13份权威SQL的SHA-256。

S4增加的16个POST映射单独记录在`s4-post-additions.json`，工具核对“原基线＋显式增量”，不会覆盖或放宽原有路由、输入字段及SQL检查。新增请求对象字段和校验另外由Java/浏览器测试覆盖。

从仓库根运行：

```bash
python java-backend/tools/check_s0_baseline.py
python java-backend/tools/verify_s1_layout.py
```

两个工具均不读运行配置、不联网、不连接数据库。前者检测声明和SQL漂移，后者同时检查五模块目录与依赖方向。它们不是完整语义解析器；必须配合Java MVC/H2/JSON测试和浏览器验收。

S4需要调整协议时，逐接口同时修改消费者及契约测试，再人工评审基线差异。不得通过日常脚本自动覆盖基线掩盖变化。`--capture`仅允许首次创建，不会覆盖现有文件。
