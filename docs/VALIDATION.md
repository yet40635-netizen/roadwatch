# 交付验证报告

验证日期：2026-09-13。环境：Windows、Python 3.12、本机 SQLite、固定演示视觉服务。未使用真实道路训练数据或业务模型权重。

## 已验证

| 验证项 | 结果 |
|---|---|
| 自动化测试 | 24项通过；算法、参数、鉴权、时序递增、状态机、审计、数据导出、租约恢复、推理失败、新增油渍/垃圾类别 |
| Python静态检查 | Ruff通过 |
| JavaScript | node --check通过 |
| 依赖一致性 | pip check通过；基础依赖锁定到验证环境版本 |
| 数据库迁移 | 临时SQLite升级→回滚→升级通过；PostgreSQL离线SQL生成通过 |
| HTTP集成 | API、Worker、Detector三个真实进程；鉴权、指标异常、事件确认/解决、图片推理、文档访问通过 |
| 视频分析链路 | OpenCV解码3秒合成视频，按1秒间隔取3帧，3个HTTP异步推理任务均成功（演示模式） |
| 文档与部署结构 | OpenAPI从代码生成；离线SVG流程页；Compose YAML及5个服务结构解析通过 |

## 本机短压测

仅测试 `GET /api/v1/overview`：100次请求、并发10、错误0、274.49 RPS、p50 30.64 ms、p95 99.92 ms。结果来自同机运行环境，有缓存和启动状态影响；不代表真实图片推理、PostgreSQL或生产高并发能力。原始结果见 `smoke-results.json`，可用 `scripts/load_test.py` 重测。

## 未完成实测的部分

- YOLO业务训练、真实道路分类准确率、测试集mAP、GPU/ONNX性能：缺少实际标注数据与权重。训练、评估和导出代码已提供。
- PostgreSQL真实实例、Docker镜像运行、AWS/OCI发布：当前没有可用Docker运行时或用户云环境。提供迁移SQL、Compose及部署步骤。
- 浏览器交互自动化/截图对比：未进行；已检查静态入口、资源HTTP响应与JS语法。
- 测试出现两条上游Starlette/httpx/anyio弃用提示，不影响本次24项测试通过；基础锁文件保留已验证版本。

真实模式新增油渍事件测试使用模拟的模型响应，仅验证类别/置信度/事件合同，不代表油渍识别效果。合成视频只验证解码与业务通路，不能用于模型评估。

## 复现

1. `setup.ps1` 安装锁定基础依赖。
2. `test.ps1` 执行测试与Python静态检查。
3. `start.ps1` 启动本机服务。
4. `python scripts/load_test.py --requests 100 --concurrency 10` 复测概览接口。
5. 安装 `requirements-ml.txt`，准备真实数据后按 `ALGORITHMS.md` 执行训练与视频接入。
