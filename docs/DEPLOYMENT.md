# 部署与运维

## 本机运行

默认 `start.ps1` 使用 Python 启动器管理 API 8010、Detector 8011 和 Worker。仅监听 127.0.0.1。API 挂载静态前端，因此没有 npm 安装步骤。

| 配置 | 默认值 | 说明 |
|---|---|---|
| DATABASE_URL | sqlite:///./data/roadwatch.db | SQLAlchemy URL；PostgreSQL 使用 postgresql+psycopg |
| DATA_DIR | ./data | 图片与默认数据库目录 |
| API_KEY | 空 | 空值仅用于本机无鉴权演示；所有 /api/v1 与 /predict 共用密钥 |
| DEMO_ENABLED | true | 控制播种接口及 Worker 接受演示输出 |
| DETECTOR_MODE | demo | demo 或 yolo |
| DETECTOR_URL | http://127.0.0.1:8011 | Worker 调用地址 |
| MODEL_PATH | ./models/road.pt | 本地权重 |
| MODEL_DEVICE | cpu | cpu 或已安装 CUDA 的设备编号 |
| EVENT_COOLDOWN_SECONDS | 120 | 同源同类同来源活动事件冷却时间 |
| JOB_LEASE_SECONDS | 180 | 任务回收租约，需超过最长推理时间 |
| POSTGRES_PASSWORD | 无 | 仅 Compose 使用，建议字母数字随机值，避免URL转义问题 |

## Docker Compose

需要 Docker Engine 与 Compose v2。设置进程变量或根目录 `.env`：

```powershell
$env:POSTGRES_PASSWORD = '替换为随机字母数字密码'
$env:API_KEY = '替换为随机密钥'
docker compose up --build -d
docker compose ps
```

默认容器仍为视觉演示模式。看板地址 http://127.0.0.1:8010，输入 API Key 后点击载入演示数据。PostgreSQL 与 Detector 不发布主机端口，API 只绑定回环地址。

真实视觉模式先准备 `models/road.pt`：

```powershell
docker build -t roadwatch:local .
$env:DEMO_ENABLED = 'false'
docker compose -f compose.yaml -f compose.ml.yaml up --build -d
```

CPU 版 ML 镜像可能较大；CUDA/GPU 镜像与设备映射需按目标硬件另行配置。增加消费进程：`docker compose up -d --scale worker=3`。Detector 当前串行推理，增加 Worker 不保证模型吞吐同比增加。

## AWS / OCI 参考部署拓扑

本次提供部署设计，不会创建云账户资源，也没有声称云上验收通过。

- 小规模：在 AWS EC2 或 OCI Compute Linux 主机运行 Compose，配置持久数据盘和数据库备份。前置反向代理提供 TLS，API 保持私网。
- 服务拆分：API 与 Worker 运行在容器平台；Detector 放 CPU/GPU 节点；PostgreSQL 使用托管数据库或专用实例；所有服务访问相同的持久图片存储。
- 多节点前必须把当前本地图片路径换为共享文件系统，或实现对象存储适配器再接 S3 / OCI Object Storage。本项目未实现 S3/OCI SDK，不能把本地路径直接当对象存储。
- 云密钥通过部署环境的秘密管理服务注入；应用当前只有共享 API Key，团队权限与个人审计需接身份网关/RBAC。
- 基础服务不提供公网速率限制、请求体全链路限制或 WAF。生产入口配置连接、超时、上传大小限制；API 已限制解码图片 10 MiB / 20 MP。

## 性能验证

```powershell
.\.venv\Scripts\python.exe scripts/load_test.py --requests 100 --concurrency 10
```

输出请求数、错误数、RPS、p50/p95，仅测试 overview 只读接口。正式容量评估需同时测试指标写入、图片上传、模型任务、实际 PostgreSQL 和 GPU，不将本机短压测外推为生产 SLA。

## 运维

1. `/health` 检查 API 与数据库；Detector `/health` 包含运行模式和模型加载状态。
2. `docker compose logs --tail=100 api worker detector` 查看错误；UI 最近任务展示失败状态。
3. PostgreSQL 做逻辑/物理备份，并同步图片卷；执行一次恢复演练。
4. 监控队列积压、失败任务比例、磁盘剩余、接口 p95 和 GPU 利用率。当前未附 Prometheus exporter。
5. 更新模型前保留旧权重与评估结果，停机替换或新实例灰度验证后切流。
6. `docker compose down` 停止服务并保留命名卷；不要使用 `-v`，除非明确需要销毁数据。

## 故障排查

| 现象 | 处理 |
|---|---|
| 8010/8011占用 | 检查已运行实例；start.ps1 -Port 可改 API 端口，Detector 固定8011 |
| 401 | 看板连接设置 / X-API-Key 与服务 API_KEY 保持一致 |
| 409指标拒绝 | 同监测点时间必须严格递增，重复时间不会重复写入 |
| 422图片失败 | 检查真实文件格式、像素数和文件字节数 |
| queued长时间不变化 | 确认 Worker 正在运行且 DATABASE_URL 与 API 相同 |
| failed推理任务 | 检查 Detector 地址、密钥、模型与日志；当前失败任务需重新提交 |
| PostgreSQL表不存在 | 执行迁移；API仅对SQLite自动建表 |
| 真实模式启动失败 | 检查模型文件、类别名、ML依赖和设备支持 |

数据库升级方式参考 [Alembic 官方命令文档](https://alembic.sqlalchemy.org/en/latest/api/commands.html)。
