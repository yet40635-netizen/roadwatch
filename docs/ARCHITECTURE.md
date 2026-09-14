# 架构与流程

系统将接入与交互留在 API，将耗时视觉计算交给独立 Detector，由 Worker 连接数据库任务队列。时序计算为有界历史窗口同步执行。默认三进程共享 SQLite 和图片目录；部署时改为 PostgreSQL 与共享持久卷。

## 服务架构

```mermaid
flowchart LR
  User[交通运营人员] --> Web[JavaScript 看板]
  Sensor[多源交通指标] --> API[FastAPI API]
  Video[本地视频抽帧工具] --> API
  Web --> API
  API --> Algo[中位数 / MAD / 拥堵规则]
  API --> DB[(SQLite / PostgreSQL)]
  API --> Images[(图片持久卷)]
  DB --> Worker[可扩展 Worker]
  Worker --> Detector[视觉 HTTP 服务]
  Images --> Worker
  Detector --> Model[固定演示 / 自定义 YOLO]
  Worker --> DB
  DB --> API
```

## 时序检测

```mermaid
flowchart TD
  Input[指标 source_id / 时间 / 速度 / 拥堵 / 流量] --> Validate[校验数值与时区]
  Validate --> Lock[锁定监测点并检查时间递增]
  Lock --> History[查询过去两小时最多60个正常样本]
  History --> Score[计算中位数基线与MAD稳健偏差]
  Score --> Check{异常规则成立?}
  Check -->|否| Normal[保存正常指标]
  Check -->|是| Cooldown{同来源同类型冷却期内有活动事件?}
  Cooldown -->|是| Reuse[复用事件]
  Cooldown -->|否| New[新建事件]
  Normal --> Commit[事务提交并返回检测原因]
  Reuse --> Commit
  New --> Commit
```

## 异步视觉任务

```mermaid
sequenceDiagram
  participant C as 看板 / 视频工具
  participant A as API
  participant D as 数据库
  participant W as Worker
  participant I as Detector
  C->>A: multipart图片 + source_id
  A->>A: 校验大小、格式，转为JPEG保存
  A->>D: 插入图片与queued任务
  A-->>C: 202 + job_id
  W->>D: 条件UPDATE获取租约令牌
  W->>I: POST /predict
  I-->>W: 检测框 + 模式 + 耗时
  W->>D: 校验令牌，事务写入结果与去重事件
  C->>A: GET /inference/jobs/{id}
  A-->>C: succeeded / failed + 结果
```

## 事件状态机

```mermaid
stateDiagram-v2
  [*] --> open
  open --> acknowledged: 人工确认
  open --> dismissed: 排除误报
  acknowledged --> resolved: 处置完成
  acknowledged --> dismissed: 排除误报
  resolved --> [*]
  dismissed --> [*]
```

跳过确认直接解决、关闭后重新打开、重复执行同一状态都会返回 409。状态条件更新防止并发覆盖，状态与操作记录在同一事务提交。审计记录当前保存时间、目标状态及备注；共享 API Key 不提供个人身份审计。

## 数据集闭环

```mermaid
flowchart LR
  Collect[采集道路图片] --> Upload[创建数据集并上传]
  Upload --> Label[框选与类别标注]
  Label --> Split[按摄像头和时间段划分数据]
  Split --> Export[导出YOLO ZIP]
  Export --> Train[训练自定义权重]
  Train --> Test[测试集评估]
  Test --> Deploy[替换权重并启用真实模式]
  Deploy --> Review[人工复核误报漏报]
  Review --> Collect
```

## 一致性与容量

- 指标写入先锁 Source 行，保证同源顺序性与冷却事件去重；不同监测点可并行。
- Worker 用条件 UPDATE 和唯一租约令牌抢占；崩溃后的任务 180 秒后可被回收，最多领取三次。
- 网络失败、返回内容非法或生产模式收到演示输出，任务立即 failed，不伪造成功结果。
- HTTP 推理超时 60 秒，应使租约时间大于最大端到端处理耗时；当前无租约心跳。
- 多 Worker 能扩展队列消费；单 Detector 用锁串行执行模型。GPU 吞吐扩展需要增加 Detector 实例和路由。
- 上传与数据库不是分布式事务：提交失败会清理新文件，但极端进程崩溃可留下孤立图片，需运维定期核对。
- SQLite 适用于本机演示；PostgreSQL 模式支持行锁。项目没有给出未经实测的高并发或秒级生产 SLA。
