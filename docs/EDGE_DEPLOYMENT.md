# 边缘部署与推理性能优化

本文档覆盖 Jetson 等边缘设备部署、INT8 量化、ONNX Runtime 推理和性能调优,用于满足岗位 JD 中"优化模型推理性能,部署到边缘设备,满足实时性要求(秒级/分钟级)"的要求。

## 1. 模型导出与量化

### 1.1 导出 ONNX

```powershell
.\.venv\Scripts\python.exe scripts\ml.py export --weights models\road.pt --imgsz 640 --device cpu
```

产出 `road.onnx`。ONNX 是跨平台推理的中间格式,可在 CPU、GPU、Jetson、NPU 上运行。

### 1.2 INT8 动态量化

量化可将模型体积缩小约 75%,CPU 推理延迟降低 30%~50%,适合边缘设备:

```powershell
.\.venv\Scripts\python.exe scripts\ml.py quantize --onnx runs\road\weights\road.onnx --output runs
```

产出 `road_int8.onnx`。终端会打印原始与量化后体积对比。

> 动态量化只量化权重(保留浮点激活),不需要校准数据集,适合道路检测这类输入分布变化大的场景。若需要更高精度,可改为静态量化并提供 100~300 张代表性图片做校准。

## 2. 推理运行时

### 2.1 ONNX Runtime(跨平台 CPU/GPU)

```python
import onnxruntime as ort
import numpy as np
from PIL import Image

session = ort.InferenceSession("road_int8.onnx", providers=["CPUExecutionProvider"])
# Jetson: providers=["TensorrtExecutionProvider", "CUDAExecutionProvider"]
image = Image.open("frame.jpg").resize((640, 640)).convert("RGB")
arr = np.array(image).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
boxes = session.run(None, {session.get_inputs()[0].name: arr})[0]
```

### 2.2 Jetson (TensorRT)

1. 在 Jetson 上安装 JetPack(自带 TensorRT)。
2. 用 `trtexec` 将 ONNX 转为 TensorRT engine:
   ```bash
   trtexec --onnx=road.onnx --saveEngine=road.engine --fp16 --workspace=4096
   ```
3. Python 推理用 `tensorrt` + `pycuda`,或继续走 ONNX Runtime 的 `TensorrtExecutionProvider`。

FP16 在 Jetson Nano/Xavier 上可带来 ~2x 提速,精度损失通常可忽略。

## 3. 延迟监控

推理服务暴露 `/stats` 接口,返回滑动窗口(默认最近 200 次)的延迟统计:

```
GET http://127.0.0.1:8011/stats
{
  "total_requests": 1280,
  "avg_ms": 62.4,
  "p50_ms": 58.1,
  "p95_ms": 110.3,
  "p99_ms": 180.7,
  "throughput_rps": 14.2,
  "uptime_seconds": 3600
}
```

可用作边缘设备健康度与实时性 SLA 的监控数据源。单帧延迟目标:CPU < 200ms,Jetson < 50ms。

## 4. 批处理

推理服务提供 `/predict_batch` 接口,一次提交最多 `MAX_BATCH`(默认 16)张图片,减少请求开销。适合视频抽帧后批量送推理:

```
POST /predict_batch
Content-Type: multipart/form-data
files: <multiple image files>
```

返回每张图的检测结果及总耗时、平均耗时。

## 5. 边缘设备部署拓扑

```
摄像头/RTSP ──► 边缘盒子(Jetson)
                ├─ 抽帧服务(FFmpeg, 1~5 FPS)
                ├─ road.engine (TensorRT 推理)
                └─ 上报 ──► RoadWatch API (/api/v1/metrics, /api/v1/inference/jobs)
                                  或 MQTT (roadwatch/metrics)
```

- 边缘侧完成推理,只上传结构化结果(框坐标、类别、置信度),节省带宽。
- 网络中断时本地缓存结果,恢复后续传。
- 模型更新通过 RoadWatch 模型版本管理接口下发,边缘端拉取新权重并热加载。

## 6. 性能调优清单

| 手段 | 预期收益 | 适用场景 |
|---|---|---|
| ONNX 导出 | 跨平台 + 20% 提速 | 所有部署 |
| INT8 量化 | 体积 -75%,延迟 -30~50% | CPU 边缘 |
| FP16 / TensorRT | 延迟 -50~70% | Jetson / GPU |
| 批处理 | 吞吐 +50~100% | 视频分析 |
| 降低 imgsz(640→416) | 延迟 -50% | 小目标少时 |
| 减少 max_det | 后处理加速 | 场景目标少 |
| Redis Stream 队列 | Worker 响应 < 100ms | 多任务高并发 |
