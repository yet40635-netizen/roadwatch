# RoadWatch · 智慧交通异常监测平台

面向 AI 算法 / 全栈开发岗位的可运行工程：道路视觉检测、交通时序异常识别、事件处置、数据集标注和服务拆分。新版扩展垃圾杂物、积水、油渍、坑洞的标注、训练、评估和图片/视频分析链路。

## 快速开始（Windows）

需要 Python 3.11 或更新版本。已有 `.venv` 可直接启动；首次安装运行：

```powershell
git clone <your-repo-url> roadwatch
cd roadwatch
.\setup.ps1 -Python py
.\start.ps1
```

若系统只有 `python` 命令，使用 `.\setup.ps1`。启动脚本同时运行 API、推理服务、Worker，并幂等载入演示数据。按 Ctrl+C 停止全部子进程。默认采用 SQLite，无需 Node.js、数据库或模型下载。

- 看板：http://127.0.0.1:8010
- 在线接口文档：http://127.0.0.1:8010/docs
- 另一种接口阅读界面：http://127.0.0.1:8010/redoc
- 视觉服务文档：http://127.0.0.1:8011/docs
- 离线流程图：打开 `docs/flows.html`

可复制 `.env.example` 为 `.env` 修改配置，启动器自动读取；独立启动 Python 模块时需要自行设置环境变量。

## 功能与岗位对应

| 岗位能力 | 项目实现 | 入口 |
|---|---|---|
| 目标检测、图像分析 | 图片上传、异步检测、归一化检测框、YOLO 自定义权重 | `inference/main.py` |
| 视频分析 | 本地视频定间隔抽帧，逐帧提交任务并等待结果，避免队列无限增长 | `scripts/video_ingest.py` |
| 时序异常 | 历史正常车速中位数、MAD 稳健偏差、拥堵联合规则 | `backend/anomaly.py` |
| 模型落地与优化 | 训练、测试集评估、ONNX 导出、设备选择、延迟记录 | `scripts/ml.py` |
| 前端可视化 | 事件看板、离线坐标图、车速趋势、图片框选标注 | `frontend/` |
| 后端 API | 参数校验、API Key、事务、状态机、分页、OpenAPI | `backend/main.py` |
| PostgreSQL | ORM、版本迁移、索引、数据库任务队列 | `migrations/` |
| 可扩展架构 | API / Worker / Detector 分离，租约抢占、多 Worker 运行 | `compose.yaml` |
| AWS / OCI | 容器部署拓扑、存储与备份、扩容和上线步骤 | `docs/DEPLOYMENT.md` |

## 扩展能力

在核心链路之外，项目还实现了以下增强模块：

| 能力 | 说明 | 入口 |
|---|---|---|
| 真实地图 | Leaflet + OpenStreetMap，监测点按经纬度落点，颜色反映告警状态 | 前端“运行总览” |
| 视频流实时检测 | 视频文件 / 摄像头按间隔抽帧，实时叠加检测框与推理延迟 | 前端“视频实时检测” |
| WebSocket 事件推送 | 新事件实时广播到看板，无需刷新 | `backend/ws.py` |
| Redis 消息队列 | 有 Redis 时自动切换 Stream 消费组，无则回退数据库轮询 | `backend/queue.py` |
| MQTT 多源接入 | 订阅 MQTT 指标消息，复用同一套异常检测逻辑 | `backend/mqtt_ingest.py` |
| 推理性能 | p50/p95/p99 延迟统计、批量推理、INT8 动态量化 | `inference/main.py`、`scripts/ml.py quantize` |
| LLM 智能分析 | 事件自动生成事态判断与处置建议；训练参数顾问；标注策略 | `backend/llm.py` |
| 模型版本管理 | 权重注册、互斥激活、推理服务自动拉取激活版本 | `model_versions` 表与 `/api/v1/model-versions` |
| 智能标注 | 模型预标注生成初始框、批量分桶 | `/images/{id}/preannotate` |
| 边缘部署 | Jetson / TensorRT / ONNX Runtime 部署与调优清单 | `docs/EDGE_DEPLOYMENT.md` |

### LLM 配置（可选）

系统兼容任何 OpenAI 风格的聊天接口（Ollama 直连或 Open WebUI）。复制 `.env.example` 为 `.env` 并设置：

```text
LLM_BASE_URL=http://127.0.0.1:11434   # Ollama 直连；Open WebUI 用 http://host:3000
LLM_API_KEY=                          # Open WebUI 需要 API Key，Ollama 留空
LLM_MODEL=qwen2.5:7b
```

LLM 不可用时所有功能自动降级，不影响事件、检测、训练等核心流程。
训练前让 LLM 推荐超参数：`python scripts/ml.py train --llm-advisor ...`。

## 十分钟演示

1. 打开看板，观察四个演示监测点、车速曲线及三条演示事件。
2. 在“监测点管理”新建一个点，提交车速 15、拥堵指数 0.9、车辆数 50。系统以初始车速 60 为基线识别拥堵。
3. 回到事件队列，打开事件，填写备注，依次“处理中”→“已解决”，查看审计记录。
4. 在“图片检测”上传道路图片，等待后台任务返回检测框。默认固定演示框不分析图片内容。
5. 在“数据集与标注”创建数据集、上传图片、拖动标框、保存，再导出 YOLO ZIP。
6. 打开 `/docs` 使用接口调试。启用 API_KEY 后，在看板“连接设置”或 Swagger 的 Authorize 中输入同一个密钥。

## 目录

```text
backend/          API、数据库模型、异常算法、事务服务、任务 Worker
inference/        独立视觉推理 HTTP 服务
frontend/         原生 JavaScript、HTML、CSS，无前端构建步骤
migrations/       Alembic 数据库版本迁移
scripts/          本机启动、训练/评估/导出、视频接入、压测、文档导出
tests/            算法、API、推理、任务恢复测试
docs/             接口文档、流程图、算法、数据库、部署、验收结果
models/           自行训练的 road.pt 或导出的模型
data/             本机数据库、转码后图片（不应提交版本库）
compose.yaml      PostgreSQL + API + Worker + Detector
```

## 文档索引

- [完整接口说明](docs/API.md)：所有接口、字段、示例、鉴权和错误码。
- [机器可读 OpenAPI](docs/openapi.json) / [推理服务 OpenAPI](docs/inference-openapi.json)。
- [架构与流程](docs/ARCHITECTURE.md) / [无需联网的流程图](docs/flows.html)。
- [算法与模型训练](docs/ALGORITHMS.md)。
- [垃圾、积水、油渍、坑洞标注规范](docs/DATASET_GUIDE.md)。
- [数据库设计](docs/DATABASE.md)。
- [容器、AWS、OCI 部署](docs/DEPLOYMENT.md)。
- [验证报告与边界](docs/VALIDATION.md)。

## 验证

```powershell
.\test.ps1
.\.venv\Scripts\python.exe -m scripts.export_openapi
.\.venv\Scripts\python.exe scripts/load_test.py --requests 100 --concurrency 10
```

默认演示模式可完整演示业务流程；尚未提供真实道路数据集与训练权重，因此不宣称真实积水/事故识别准确率。坐标图是离线经纬度分布图；视频工具提供抽帧分析，不包含连续目标跟踪、事故因果判断或 RTSP 流服务。云部署配置已交付，未在用户云账户中创建资源。
