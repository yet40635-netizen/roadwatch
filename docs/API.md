# 完整接口参考

API 基址 `http://127.0.0.1:8010`；独立推理服务基址 `http://127.0.0.1:8011`。文档下半部分从应用 OpenAPI 自动生成，覆盖每个接口的请求参数、响应模型及所有字段。修改接口后执行 `python -m scripts.export_openapi` 更新。

## 通用约定

- 所有 `/api/v1/*` 和推理服务 `/predict` 使用 `X-API-Key`；设置为空时允许本机演示访问。`/health`、静态页面和文档可直接访问。
- JSON 请求使用 `application/json`，上传使用 `multipart/form-data`，文件字段固定为 `file`。
- ID 为服务生成的 UUID 字符串。时间存为带 UTC 时区的 ISO8601 字符串。
- 指标时间必须有时区、不超过服务器未来五分钟、同监测点严格递增。重复或乱序返回409。
- 车速单位 km/h；拥堵指数0~1；volume是该次观测窗口车辆数，采集端自行统一观测窗口（建议一分钟）。
- 枚举：water积水、obstacle道路障碍、accident事故、pothole坑洞、oil油渍、garbage垃圾杂物、congestion拥堵、speed_drop异常降速。
- 检测框/标注框使用归一化左上角 `x,y` 与 `width,height`，不是YOLO中心坐标。导出时转换为中心坐标。
- 视觉类别ID顺序固定：0 water、1 obstacle、2 accident、3 pothole、4 oil、5 garbage。`GET /api/v1/labels` 可读取。

## 典型请求

PowerShell 新建监测点并提交异常指标：

```powershell
$base = 'http://127.0.0.1:8010/api/v1'
$headers = @{ 'X-API-Key' = '' }
$source = Invoke-RestMethod "$base/sources" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"name":"Road A","latitude":22.28,"longitude":114.16,"baseline_speed":60}'
$body = @{source_id=$source.id; observed_at=[DateTimeOffset]::UtcNow.ToString('o'); speed=12; congestion=0.92; volume=40} | ConvertTo-Json
Invoke-RestMethod "$base/metrics" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod "$base/events?status=open&limit=10&offset=0" -Headers $headers
```

响应关键内容示例（UUID与时间按实际生成）：

```json
{"speed":12,"congestion":0.92,"anomaly":true,"score":9.6,"baseline":60,"reason":"速度 12.0 km/h，基线 60.0 km/h，稳健偏差 9.60，拥堵指数 0.92"}
```

图片推理：`POST /api/v1/inference/jobs` multipart包括 `source_id` 和 `file`，返回202与 `queued` 任务；以返回ID轮询 `GET /api/v1/inference/jobs/{job_id}`。成功结果含 `mode/model/latency_ms/detections/warning`，失败结果含 `error`。默认演示框不能用于模型精度评价。

标注示例：

```json
{"split":"train","annotations":[{"label":"oil","x":0.1,"y":0.2,"width":0.3,"height":0.4},{"label":"garbage","x":0.6,"y":0.6,"width":0.1,"height":0.2}]}
```

发送到 `PUT /api/v1/images/{image_id}/annotations`，整体替换该图标注。只允许数据集图片；不允许给孤立推理图片标注。`GET /datasets/{dataset_id}/export` 返回 application/zip，包括图片、标签和data.yaml。

## 状态、分页与限制

事件状态仅允许 `open→acknowledged/dismissed` 和 `acknowledged→resolved/dismissed`。PATCH请求体 `{"status":"acknowledged","note":"现场已确认"}`；非法转换或并发竞争返回409。操作记录从 `/events/{event_id}/actions` 获取。

events返回 `{items,total,limit,offset}`，limit默认30最大100。metrics返回按观测时间升序排列的最近记录，limit默认60最大1000。sources/datasets最多1000条。dataset images使用limit/offset、默认100最大500；jobs默认30最大100。其他列表为数组，不含total。

上传仅JPEG/PNG/WebP、最大10MiB、最大20MP；图片转JPEG，移除原元数据。最多500个标注/检测框。交互导出最多500张图片、原图文件合计100MiB。数据为空或文件缺失返回409。导出是内存ZIP，仅面向小规模标注演示。

## 错误结构

API业务错误：`{"error":{"message":"说明"}}`。参数错误：`{"error":{"message":"Request validation failed","details":[{"field":"body.speed","message":"说明"}]}}`。

推理服务使用FastAPI默认格式：`{"detail":"说明"}`；框架参数校验的detail为数组。主API的OpenAPI统一登记自定义错误模型，推理接口保留默认HTTPValidationError。

| HTTP状态 | 原因 |
|---|---|
| 200 / 201 / 202 | 查询或更新成功 / 已创建 / 任务已接受 |
| 401 | 缺少或错误API Key |
| 403 | 演示播种被关闭 |
| 404 | 关联资源、图片文件不存在 |
| 409 | 同名数据集、指标重复/乱序、非法状态转换、空导出、非数据集图片标注 |
| 413 | 图片或导出体积超限 |
| 422 | 参数、时间、枚举、图片格式或标注越界 |
| 500 | 未处理服务端故障，查看服务日志 |

没有通用幂等键。重复POST图片/监测点可能新建记录；指标(source_id, observed_at)唯一；demo/seed幂等。当前鉴权是共享API Key，不支持个人登录或按角色授权。


## RoadWatch API

### GET `/health`

Health

- `200`：Successful Response；HealthOut

### GET `/api/v1/labels`

Labels

- `200`：Successful Response；array<LabelOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/overview`

Overview

- `200`：Successful Response；OverviewOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/demo/seed`

Demo Seed

- `201`：Successful Response；HealthOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/sources`

Sources

- `200`：Successful Response；array<SourceOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/sources`

Create Source

请求体：`application/json` → **SourceCreate**。

- `201`：Successful Response；SourceOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/metrics`

Ingest Metric

请求体：`application/json` → **MetricCreate**。

- `201`：Successful Response；MetricOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/metrics`

Metrics

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| source_id | query | True | `{"type": "string", "title": "Source Id"}` |
| limit | query | False | `{"type": "integer", "maximum": 1000, "minimum": 1, "default": 60, "title": "Limit"}` |

- `200`：Successful Response；array<MetricOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/events`

Events

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| status | query | False | `{"anyOf": [{"enum": ["open", "acknowledged", "resolved", "dismissed"], "type": "string"}, {"type": "null"}], "title": "Status"}` |
| kind | query | False | `{"anyOf": [{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage", "congestion", "speed_drop"], "type": "string"}, {"type": "null"}], "title": "Kind"}` |
| source_id | query | False | `{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Source Id"}` |
| limit | query | False | `{"type": "integer", "maximum": 100, "minimum": 1, "default": 30, "title": "Limit"}` |
| offset | query | False | `{"type": "integer", "minimum": 0, "default": 0, "title": "Offset"}` |

- `200`：Successful Response；EventPage
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/events/{event_id}`

Event Detail

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| event_id | path | True | `{"type": "string", "title": "Event Id"}` |

- `200`：Successful Response；EventOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### PATCH `/api/v1/events/{event_id}`

Update Event

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| event_id | path | True | `{"type": "string", "title": "Event Id"}` |

请求体：`application/json` → **ActionCreate**。

- `200`：Successful Response；EventOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/events/{event_id}/actions`

Event Actions

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| event_id | path | True | `{"type": "string", "title": "Event Id"}` |

- `200`：Successful Response；array<ActionOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/datasets`

Datasets

- `200`：Successful Response；array<DatasetOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/datasets`

Create Dataset

请求体：`application/json` → **DatasetCreate**。

- `201`：Successful Response；DatasetOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/datasets/{dataset_id}/images`

Upload Dataset Image

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| dataset_id | path | True | `{"type": "string", "title": "Dataset Id"}` |

请求体：`multipart/form-data` → **Body_upload_dataset_image_api_v1_datasets__dataset_id__images_post**。

- `201`：Successful Response；ImageOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/datasets/{dataset_id}/images`

Dataset Images

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| dataset_id | path | True | `{"type": "string", "title": "Dataset Id"}` |
| limit | query | False | `{"type": "integer", "maximum": 500, "minimum": 1, "default": 100, "title": "Limit"}` |
| offset | query | False | `{"type": "integer", "minimum": 0, "default": 0, "title": "Offset"}` |

- `200`：Successful Response；array<ImageOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### PUT `/api/v1/images/{image_id}/annotations`

Annotate

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| image_id | path | True | `{"type": "string", "title": "Image Id"}` |

请求体：`application/json` → **AnnotationUpdate**。

- `200`：Successful Response；ImageOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/images/{image_id}/content`

Image Content

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| image_id | path | True | `{"type": "string", "title": "Image Id"}` |

- `200`：Successful Response；
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/datasets/{dataset_id}/export`

Export Dataset

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| dataset_id | path | True | `{"type": "string", "title": "Dataset Id"}` |

- `200`：Successful Response；
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### POST `/api/v1/inference/jobs`

Create Job

请求体：`multipart/form-data` → **Body_create_job_api_v1_inference_jobs_post**。

- `202`：Successful Response；JobOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/inference/jobs`

Jobs

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| limit | query | False | `{"type": "integer", "maximum": 100, "minimum": 1, "default": 30, "title": "Limit"}` |

- `200`：Successful Response；array<JobOut>
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

### GET `/api/v1/inference/jobs/{job_id}`

Job Detail

| 参数 | 位置 | 必填 | 类型与约束 |
|---|---|---|---|
| job_id | path | True | `{"type": "string", "title": "Job Id"}` |

- `200`：Successful Response；JobOut
- `401`：Unauthorized；ErrorResponse
- `403`：Forbidden；ErrorResponse
- `404`：Not Found；ErrorResponse
- `409`：Conflict；ErrorResponse
- `413`：Request Entity Too Large；ErrorResponse
- `422`：Unprocessable Entity；ErrorResponse

## RoadWatch API 字段字典

### ActionCreate

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| status | True | string | `{"enum": ["open", "acknowledged", "resolved", "dismissed"]}` |
| note | False | string | `{"maxLength": 1000, "default": ""}` |

### ActionOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | string | `{}` |
| event_id | True | string | `{}` |
| status | True | string | `{"enum": ["open", "acknowledged", "resolved", "dismissed"]}` |
| note | True | string | `{}` |
| created_at | True | string | `{}` |

### AnnotationUpdate

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| split | True | string | `{"enum": ["train", "val", "test"]}` |
| annotations | True | array<Box> | `{"maxItems": 500}` |

### Body_create_job_api_v1_inference_jobs_post

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| source_id | True | string | `{}` |
| file | True | string | `{"contentMediaType": "application/octet-stream"}` |

### Body_upload_dataset_image_api_v1_datasets__dataset_id__images_post

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| file | True | string | `{"contentMediaType": "application/octet-stream"}` |

### Box

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| label | True | string | `{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage"]}` |
| x | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| y | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| width | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |
| height | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |

### DatasetCreate

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| name | True | string | `{"maxLength": 100, "minLength": 1}` |
| description | False | string | `{"maxLength": 2000, "default": ""}` |

### DatasetOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| name | True | string | `{"maxLength": 100, "minLength": 1}` |
| description | False | string | `{"maxLength": 2000, "default": ""}` |
| id | True | string | `{}` |
| created_at | True | string | `{}` |

### Detection

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| label | True | string | `{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage"]}` |
| x | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| y | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| width | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |
| height | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |
| confidence | True | number | `{"maximum": 1.0, "minimum": 0.0}` |

### DetectionResult

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| mode | True | string | `{"enum": ["demo", "yolo"]}` |
| model | True | string | `{}` |
| latency_ms | True | number | `{"minimum": 0.0}` |
| detections | True | array<Detection> | `{"maxItems": 500}` |
| warning | False | string / null | `{}` |

### ErrorDetail

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| field | True | string | `{}` |
| message | True | string | `{}` |

### ErrorMessage

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| message | True | string | `{}` |
| details | False | array<ErrorDetail> / null | `{}` |

### ErrorResponse

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| error | True | ErrorMessage | `{}` |

### EventOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | string | `{}` |
| source_id | True | string | `{}` |
| kind | True | string | `{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage", "congestion", "speed_drop"]}` |
| severity | True | string | `{"enum": ["medium", "high"]}` |
| status | True | string | `{"enum": ["open", "acknowledged", "resolved", "dismissed"]}` |
| confidence | True | number / null | `{}` |
| description | True | string | `{}` |
| origin | True | string | `{"enum": ["demo", "vision", "timeseries"]}` |
| image_id | True | string / null | `{}` |
| created_at | True | string | `{}` |
| updated_at | True | string | `{}` |

### EventPage

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| items | True | array<EventOut> | `{}` |
| total | True | integer | `{}` |
| limit | True | integer | `{}` |
| offset | True | integer | `{}` |

### HealthOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| status | True | string | `{}` |
| service | True | string | `{}` |

### ImageOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | string | `{}` |
| dataset_id | True | string / null | `{}` |
| filename | True | string | `{}` |
| width | True | integer | `{}` |
| height | True | integer | `{}` |
| split | True | string | `{}` |
| annotations | True | array<Box> | `{}` |
| created_at | True | string | `{}` |

### JobOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | string | `{}` |
| source_id | True | string | `{}` |
| image_id | True | string | `{}` |
| status | True | string | `{"enum": ["queued", "running", "succeeded", "failed"]}` |
| result | True | DetectionResult / null | `{}` |
| error | True | string / null | `{}` |
| attempts | True | integer | `{}` |
| created_at | True | string | `{}` |
| updated_at | True | string | `{}` |

### LabelOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | integer | `{}` |
| label | True | string | `{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage"]}` |
| name | True | string | `{}` |

### MetricCreate

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| source_id | True | string | `{}` |
| observed_at | True | string (date-time) | `{"format": "date-time"}` |
| speed | True | number | `{"maximum": 250.0, "minimum": 0.0}` |
| congestion | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| volume | True | integer | `{"maximum": 100000.0, "minimum": 0.0}` |

### MetricOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| id | True | string | `{}` |
| source_id | True | string | `{}` |
| observed_at | True | string | `{}` |
| speed | True | number | `{}` |
| congestion | True | number | `{}` |
| volume | True | integer | `{}` |
| anomaly | True | boolean | `{}` |
| score | True | number | `{}` |
| baseline | True | number | `{}` |
| reason | True | string | `{}` |

### OverviewOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| sources | True | integer | `{}` |
| open_events | True | integer | `{}` |
| high_events | True | integer | `{}` |
| queued_jobs | True | integer | `{}` |
| demo_enabled | True | boolean | `{}` |

### SourceCreate

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| name | True | string | `{"maxLength": 100, "minLength": 1}` |
| latitude | True | number | `{"maximum": 90.0, "minimum": -90.0}` |
| longitude | True | number | `{"maximum": 180.0, "minimum": -180.0}` |
| baseline_speed | False | number | `{"maximum": 200.0, "exclusiveMinimum": 0.0, "default": 60}` |

### SourceOut

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| name | True | string | `{"maxLength": 100, "minLength": 1}` |
| latitude | True | number | `{"maximum": 90.0, "minimum": -90.0}` |
| longitude | True | number | `{"maximum": 180.0, "minimum": -180.0}` |
| baseline_speed | False | number | `{"maximum": 200.0, "exclusiveMinimum": 0.0, "default": 60}` |
| id | True | string | `{}` |
| created_at | True | string | `{}` |


## RoadWatch Inference

### GET `/health`

Health

- `200`：Successful Response；object

### POST `/predict`

Predict

请求体：`multipart/form-data` → **Body_predict_predict_post**。

- `200`：Successful Response；DetectionResult
- `422`：Validation Error；HTTPValidationError

## RoadWatch Inference 字段字典

### Body_predict_predict_post

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| file | True | string | `{"contentMediaType": "application/octet-stream"}` |

### Detection

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| label | True | string | `{"enum": ["water", "obstacle", "accident", "pothole", "oil", "garbage"]}` |
| x | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| y | True | number | `{"maximum": 1.0, "minimum": 0.0}` |
| width | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |
| height | True | number | `{"maximum": 1.0, "exclusiveMinimum": 0.0}` |
| confidence | True | number | `{"maximum": 1.0, "minimum": 0.0}` |

### DetectionResult

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| mode | True | string | `{"enum": ["demo", "yolo"]}` |
| model | True | string | `{}` |
| latency_ms | True | number | `{"minimum": 0.0}` |
| detections | True | array<Detection> | `{"maxItems": 500}` |
| warning | False | string / null | `{}` |

### HTTPValidationError

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| detail | False | array<ValidationError> | `{}` |

### ValidationError

| 字段 | 必填 | 类型 | 约束 / 默认值 |
|---|---|---|---|
| loc | True | array<string / integer> | `{}` |
| msg | True | string | `{}` |
| type | True | string | `{}` |
| input | False | object | `{}` |
| ctx | False | object | `{}` |
