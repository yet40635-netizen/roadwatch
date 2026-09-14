# 数据库设计

开发默认 SQLite（WAL、外键检查、30 秒锁等待）；部署使用 PostgreSQL 与 psycopg 驱动。时间统一存 UTC ISO8601 毫秒字符串，当前模型有意保持两种数据库一致；大规模时序存储可迁移为 PostgreSQL timestamptz 与按时间分区。

| 表 | 主键 | 关联 | 关键数据 |
|---|---|---|---|
| sources | id UUID字符串 | 无 | 名称、经纬度、初始车速、创建时间 |
| metrics | id | source_id → sources | 观测时间、速度、拥堵、车流、异常、得分、基线、原因 |
| events | id | source_id → sources | 类型、级别、状态、来源、置信度、图片ID、描述、时间 |
| event_actions | id | event_id → events | 状态、备注、时间 |
| datasets | id | 无 | 唯一名称、描述、时间 |
| images | id | dataset_id → datasets，可空 | 原文件名、尺寸、split、JSON标注 |
| jobs | id | source_id → sources；image_id → images | 状态、JSON结果、错误、尝试次数、租约令牌和到期时间 |

`events.image_id` 是可空逻辑关联，当前未设物理外键。每张图片实际保存在 `DATA_DIR/images/{id}.jpg`，数据库不存二进制图片。

## 索引

- metrics：`(source_id, observed_at)` 唯一约束，另有同字段查询索引。
- events：`(source_id, kind, created_at)` 冷却查询索引、status 索引、created_at 索引。
- event_actions：event_id 索引。
- datasets：name 唯一约束。
- jobs：status 索引。队列增大后可按 PostgreSQL 查询计划增加 status/lease_until/created_at 复合索引。

## ER 图

```mermaid
erDiagram
  sources ||--o{ metrics : receives
  sources ||--o{ events : emits
  sources ||--o{ jobs : submits
  events ||--o{ event_actions : records
  datasets o|--o{ images : contains
  images ||--o{ jobs : analyzed
```

## 初始化与升级

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://user:password@localhost:5432/roadwatch'
.\.venv\Scripts\python.exe -m alembic upgrade head
```

迁移读取进程环境变量，不自动读取 `.env`。Compose 的 migrate 服务会先执行迁移，成功后再启动 API。`migrations/versions/0001_initial.py` 为独立冻结结构，不依赖后续模型代码变化。`docs/schema.postgresql.sql` 是离线编译产物，可供 DBA 评审；推荐执行 Alembic 管理版本。

已有本机 SQLite 使用 create_all 自动建表。不要对已有未登记版本的库直接执行初始迁移；只有确认表结构与 0001 完全一致并备份后，才可 `alembic stamp 0001`，再升级后续版本。

数据留存没有自动删除任务。备份时必须同时保存数据库和图片卷；只备份数据库无法恢复检测原图。恢复后检查图片记录与文件一致性。
