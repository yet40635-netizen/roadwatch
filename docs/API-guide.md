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
