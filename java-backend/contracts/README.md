# 当前业务接口与SQL契约

`api-contract.json`是唯一有效清单，记录六个正式Controller的路由/HTTP状态声明、输入字段、14张业务表、3个视图和13份SQL的SHA-256。Java业务只使用POST，GET仅限健康检查。旧S0基线与POST增量叠加清单已删除，历史内容可通过Git查阅。

从仓库根运行：

```bash
python java-backend/tools/check_contract.py
python java-backend/tools/verify_s1_layout.py
```

工具只读取源码，不连接数据库、网络或运行配置。检查器明确拒绝正式Controller出现健康以外GET及PUT/PATCH/DELETE，并比较完整路由清单和SQL校验和。接口变更必须同时更新调用方、清单及行为测试；脚本不会自动覆盖现有清单。

本次因用户明确取消兼容而更新HTTP清单，原输入字段、表/视图及13份SQL校验和逐项确认未变。所有旧页面GET/PUT和对应Python算法读取别名均有实际HTTP拒绝测试；健康检查继续GET。
