# 模型与密钥配置

`godp_system_config` 只保留当前需要的 8 项：服务监听地址与端口、模型标识、鉴权密钥。Worker 开关、轮询间隔、超时等采用代码默认值；后续确实需要运营调整时再加入配置表。

## 当前配置项

| 配置键 | 用途 | 是否需要填写 |
| --- | --- | --- |
| `BACKEND_HOST` / `BACKEND_PORT` | 后端监听地址和端口 | 默认 `0.0.0.0:6930` |
| `FRONTEND_HOST` / `FRONTEND_PORT` | 前端监听地址和端口 | 默认 `0.0.0.0:930` |
| `ARK_API_KEY` | 火山方舟 API 鉴权密钥 | 使用豆包时必填 |
| `MODEL_NAME` | 全项目共用的文本生成模型或方舟接入点 ID | 已有默认值，通常不用改 |
| `EMBEDDING_MODEL_NAME` | 全项目共用的语义向量模型或方舟接入点 ID；T6、选题画像、账号画像统一使用 | 已有默认值，通常不用改 |
| `INTEGRATION_TOKEN` | 项目内部及平台对接接口的鉴权密钥 | 对接接口时配置 |

项目只有两类模型配置：文本生成使用 `MODEL_NAME`，向量生成统一使用 `EMBEDDING_MODEL_NAME`。选题标签中的 T6、选题画像向量和账号画像向量共用同一个向量模型。两类调用共用 `ARK_API_KEY`。向量请求使用方舟 `/embeddings/multimodal` 接口并只发送文本；模型或接入点须已开通并支持该接口。

## 更新密钥或模型

在 `backend` 目录执行。密钥通过隐藏输入读取，不会显示在终端命令历史中：

```powershell
python -c "import getpass,subprocess,sys; v=getpass.getpass('ARK_API_KEY: '); r=subprocess.run([sys.executable,'-m','app.system_config','set','ARK_API_KEY','--stdin'],input=v,text=True); raise SystemExit(r.returncode)"
```

设置模型接入点 ID：

```powershell
python -m app.system_config set EMBEDDING_MODEL_NAME --value 实际接入点ID
```

查看配置时，密钥会脱敏：

```powershell
python -m app.system_config list
```

## 迁移说明

重新执行 `python -m app.init_system_config` 会确保当前 8 项配置存在，恢复之前停用的四项监听地址/端口，并物理删除配置表中其余参数。监听地址/端口会保留原值；模型名称与密钥也不会被覆盖。`python -m app.init_db` 同样执行清理。

数据库连接信息仍只放在项目根目录 `.env`；密钥不要写进 `.env`、前端代码或 Git。
