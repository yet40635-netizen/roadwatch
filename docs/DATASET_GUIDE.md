# 道路专项数据集与标注规范

新增要求对应六类视觉目标。训练目标是图片/视频帧上的道路目标框；仅凭静态画面不能确认事故成因或油品成分，业务事件仍需人工核查。

| ID | 标签 | 定义 | 易混淆情况 |
|---|---|---|---|
| 0 | water | 路面可见积水、水浸区域 | 阴影、反光、普通湿路面 |
| 1 | obstacle | 阻碍道路通行的大件物体 | 正常停靠设施、非车道物体 |
| 2 | accident | 可见事故场景，例如碰撞车辆与明显散落物 | 正常拥堵、路边停靠；不从单张图推断隐蔽碰撞 |
| 3 | pothole | 可见路面凹坑、破损坑洞 | 井盖、补丁、阴影 |
| 4 | oil | 具有油污外观的路面污染区域 | 水渍、彩色反光、材质色差；疑似情况单独复核 |
| 5 | garbage | 路面垃圾、散落杂物 | 路边垃圾桶、车道外景物 |

## 采集与划分

覆盖白天/夜晚、晴雨、不同摄像头高度和道路材质。保留没有异常的负样本，并明确记录采集地点、日期、相机与天气。先按摄像头/日期分组，再划分train/val/test；相邻视频帧全部放在同一划分。

框应尽量贴合可见目标；同一目标不要同时标为garbage和obstacle。散落小物体可逐个标框；大面积水/油区域使用包围框，若需要精确面积，后续应改用实例分割与多边形标注（本版未实现）。

不要使用演示固定框或合成测试视频作为实际模型质量证据。页面人工标注是训练数据来源，推理结果不自动写为真值。

## 检查与训练命令

```powershell
.\.venv\Scripts\python.exe scripts/check_dataset.py datasets/roads
.\.venv\Scripts\python.exe scripts/ml.py train --weights models/base.pt --data datasets/roads/data.yaml --epochs 50
.\.venv\Scripts\python.exe scripts/ml.py evaluate --weights runs/road/weights/best.pt --data datasets/roads/data.yaml
```

check_dataset校验三种划分存在、标签行格式、类别范围、数值有限性、框边界、重复图片跨集合泄漏；空标签文件表示负样本。它不验证标注语义，也不能发现所有近似帧泄漏。训练入口另外验证六类名称与顺序一致。

## 验收记录

记录每类precision/recall、mAP50/mAP50-95、混淆情况、不同天气/时段误报、事件发现延迟、模型大小、设备和输入分辨率。阈值由实际业务验收确定，本项目不预填未经测量的准确率。建议结合误报复核建立下一轮数据采集计划。
