# 算法与模型

## 时序异常

输入：当前车速 v（km/h）、拥堵指数 c（0~1）、同源历史正常车速 H、配置初始正常车速 f。

历史窗口：当前观测时间之前两小时，最多 60 条，排除曾被标记异常的样本；当前点不加入计算，避免未来信息泄漏。

```text
b = median(H)                       当正常样本数 >= 5
b = f                               冷启动阶段
MAD = median(abs(h - b))             正常样本数 >= 5，否则为0
scale = max(1.4826 * MAD, 5)
score = max(0, (b - v) / scale)
speed_drop = v < 0.6*b 且 score >= 3
congestion = c >= 0.8 且 v < 0.5*b
anomaly = speed_drop 或 congestion
```

拥堵优先于异常降速分类。尺度下限 5 防止稳定序列 MAD 为零。默认同监测点、同类型、同来源的活动事件在 120 秒内合并，冷却依据事件入库时间。车流量保存用于展示/扩展，当前不参与判别。

限制：规则可解释，但不能取代季节性、节假日、降雨与道路施工建模；持续缓慢变化可能导致基线滞后。正式评估需按时间切分训练与测试，报告事件级 precision/recall、误报数/摄像头小时、发现延迟，而不是只汇报点级准确率。

## 视觉推理

`DETECTOR_MODE=demo` 返回固定障碍物演示框和醒目标记，不读取图像语义。`DETECTOR_MODE=yolo` 加载本地自定义权重，只接受类别 water、obstacle、accident、pothole、oil、garbage 的非空子集。通用 COCO 模型不能直接识别这些道路事件，因此不会将车辆检测误当事故检测。

真实推理使用 `conf=0.4`、归一化 xyxy 转左上角 x/y/width/height，裁剪到 [0,1]。延迟包含解码、等待模型锁及计算。当前模型结果最多返回 500 个框；服务间还使用 Pydantic 验证。

## 数据准备与训练

在界面导出 ZIP 后先解压到 `datasets/roads`。训练、验证与测试集都需要实际图片；按摄像头/采集日期分组分割，连续帧不要跨集合。类顺序固定为 water、obstacle、accident、pothole、oil、garbage。请人工审核漏框、错类与负样本。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe scripts/check_dataset.py datasets/roads
.\.venv\Scripts\python.exe scripts/ml.py train --weights models/base.pt --data datasets/roads/data.yaml --epochs 50 --device cpu
.\.venv\Scripts\python.exe scripts/ml.py evaluate --weights runs/road/weights/best.pt --data datasets/roads/data.yaml
.\.venv\Scripts\python.exe scripts/ml.py export --weights runs/road/weights/best.pt
```

`base.pt` 需自行准备合适的本地预训练权重；工具不自动下载权重。训练完成的保存目录以训练日志为准，已有运行可能产生递增目录。评估输出 `runs/evaluation.json`，包含测试集指标及模型阶段速度。导出的 ONNX 位于权重附近。

复制训练后的权重为 `models/road.pt`，设置 `.env` 中 `DETECTOR_MODE=yolo`、`DEMO_ENABLED=false`，重启。CUDA 环境可设置 `MODEL_DEVICE=0`，CPU 用 `cpu`。未提供权重时真实服务明确启动失败。

ONNX 导出工具用于边缘部署实验；当前在线服务默认验收路径为 PT 权重，不把导出文件自动接入服务。进一步可评估 ONNX Runtime / TensorRT、输入分辨率、FP16/INT8 的延迟与精度损失，只有实际评估后才能选型。

## 视频接入

```powershell
$env:API_KEY = '与服务一致的密钥'
.\.venv\Scripts\python.exe scripts/video_ingest.py samples/road.mp4 --source-id '监测点ID' --interval 5 --max-frames 120
```

依赖 OpenCV。对本地视频按媒体帧率抽样，每次只允许一个在途任务；标准输出记录视频偏移与任务 ID。事件时间为处理入库时间，原始视频偏移记录在工具输出中。工具不支持实时 RTSP、目标跟踪或轨迹速度计算，也不将视频帧率推算成车速。

## 参考资料

- [Ultralytics Python 调用方式](https://docs.ultralytics.com/usage/python/)
- [Ultralytics 训练](https://docs.ultralytics.com/modes/train/)
- [Ultralytics 模型导出](https://docs.ultralytics.com/modes/export/)

代码按上述官方接口实现；训练依赖、权重和 GPU 没有在当前环境进行完整验收。
