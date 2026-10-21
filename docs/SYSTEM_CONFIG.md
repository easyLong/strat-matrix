# MySQL 系统配置

项目根目录 `.env` 只保留 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。这些连接参数负责定位数据库；端口、模型地址、模型密钥、内部接口令牌、Worker 开关、超时及重试等参数统一存放在 `godp_system_config`。

现有 `godp_strategy_config` 继续保存运营页面中的内容策划、生命周期、经营策略与标签字典；匹配算法策略仍保存在原有策略版本表。系统配置表负责程序运行参数。

## 表结构

建表语句位于 `backend/schema.sql`。表及全部 14 个字段均有中文注释。

| 字段 | 含义 |
| --- | --- |
| `id` | 配置记录主键 |
| `config_key` | 配置唯一键，区分大小写，沿用原参数名称 |
| `config_group` | 分组：server、integration、doubao、labeling、topic_vector、account_vector、preparation、matching、scheduler |
| `config_name` | 配置项中文名称与用途 |
| `config_value` | 配置值文本；数值和开关按声明类型解析 |
| `value_type` | string、int、bool；开关使用 0/1 |
| `is_secret` | 是否为密钥或令牌；查询时脱敏 |
| `enabled` | 1 启用，0 停用；读取停用参数会报错 |
| `version` | 修改时递增，支持并发版本检查 |
| `create_time`、`create_by` | 创建时间与创建来源 |
| `update_time`、`update_by` | 最后修改时间与来源 |
| `del_flag` | 逻辑删除标记，N 正常、Y 删除 |

当前内置 43 个运行配置定义，完整清单及中文用途位于 `backend/app/system_config_catalog.py`。密钥在数据库中作为受控配置值保存，命令行列表始终脱敏；前端启动只接收四个非敏感监听/代理参数。

## 创建与迁移

先配置 MySQL 连接并安装后端依赖。在 `backend` 目录执行：

```bash
python -m app.init_system_config --migrate-env --clean-env
```

命令会创建配置表、导入旧根目录及 `docs/.env` 中的非 MySQL 参数，并补齐默认配置。根目录的同名参数优先。只有事务提交并逐项核对成功后才清理旧文件，MySQL 密码中的引号、空格等会正确保留。发生数据库值冲突时不覆盖已有配置，也不清理原文件。

仅补建表和缺失默认项：

```bash
python -m app.init_system_config
```

重复执行不覆盖数据库现有值。常规 `python -m app.init_db` 也包含建表及补齐缺失项，不会重置已有系统配置。

## 查询与修改

```bash
python -m app.system_config list
python -m app.system_config list --group doubao
python -m app.system_config set DOUBAO_EMBEDDING_MODEL --value 实际模型或接入点ID
python -m app.system_config set TOPIC_LABEL_WORKER_ENABLED --value 1
```

密钥通过标准输入设置，避免放进命令行参数。Bash 示例：

```bash
read -rsp 'Ark API Key: ' config_secret
printf '%s' "$config_secret" | python -m app.system_config set ARK_API_KEY --stdin
unset config_secret
```

新数据库还需设置 `INTEGRATION_TOKEN`；旧环境迁移会保留原令牌。豆包 API Key、向量模型为空时，打标进程保持关闭，按[豆包打标说明](DOUBAO_TOPIC_LABELING.md)填写后再启用。

也可通过数据库管理工具修改：

```sql
SELECT config_key, config_name, config_group, value_type, enabled, version
FROM godp_system_config
WHERE del_flag = 'N'
ORDER BY config_group, id;

UPDATE godp_system_config
SET config_value = '930', version = version + 1, update_by = '运营配置'
WHERE config_key = 'FRONTEND_PORT' AND del_flag = 'N';
```

直接 SQL 修改时请递增版本。程序使用最长约 5 秒的配置缓存；端口、进程开关和常驻 Worker 在启动时读取，修改后重启相关服务。轮换内部令牌时同时重启持有令牌的调用进程。数据库不可用时，过期缓存不会继续使用旧密钥；缺失或停用的配置也不会退回 `.env` 或同名环境变量。

## 启动链路

- `start.sh`、`status.sh` 经 `system-config.sh` 从 MySQL 读取非敏感启动参数。
- `stop.sh` 正常读取配置中的进程目录；数据库故障时保留默认目录或显式 `RUN_DIR` 的应急停止能力。
- 前端 `npm run dev` / `npm run preview` 调用 Python 的 `frontend-json` 命令，只获得后端/前端的监听地址和端口。数据库连接、模型密钥和内部令牌不会进入浏览器资源。
- `npm run build` 只编译静态资源，不要求数据库可用。
- `APP_ROOT`、`PYTHON_BIN`、`NPM_BIN` 是定位项目和解释器的启动引导选项，可通过命令行指定，不写入 `.env`。应用端口和开关以数据库为准。

## 验证

```bash
cd backend
python -m unittest discover -s tests -p test_system_config.py -v
python -m unittest discover -s tests -v
```

测试覆盖配置源唯一性、密钥脱敏、前端导出白名单、缓存及故障处理、并发版本检查、中文注释、迁移幂等性、文件清理顺序和 MySQL 密码保留。
