import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Train, evaluate, export or quantize a road detector")
    parser.add_argument("action", choices=["train", "evaluate", "export", "quantize"])
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--onnx", type=Path, help="Input ONNX model for quantize action")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    parser.add_argument("--llm-advisor", action="store_true",
                        help="Ask local LLM for training parameter suggestions before training")
    args = parser.parse_args()

    if args.action == "quantize":
        if args.onnx is None or not args.onnx.is_file():
            parser.error("--onnx must point to an existing ONNX model for quantize")
        return quantize_model(args.onnx, args.output)

    if args.weights is None or not args.weights.is_file():
        parser.error("Provide local weights; this tool does not download a model implicitly")
    if args.action != "export" and (args.data is None or not args.data.is_file()):
        parser.error("--data must point to an extracted dataset data.yaml")
    if args.epochs < 1 or args.imgsz < 32:
        parser.error("epochs must be positive and imgsz must be at least 32")
    import yaml
    from ultralytics import YOLO

    if args.action != "export":
        from check_dataset import LABELS, check_dataset

        dataset = yaml.safe_load(args.data.read_text(encoding="utf-8"))
        names = dataset.get("names", {})
        names = [names[index] for index in sorted(names)] if isinstance(names, dict) else names
        if names != LABELS:
            parser.error("Dataset classes must match the six RoadWatch classes in order")
        report = check_dataset(args.data.resolve().parent)
        if not report["valid"]:
            parser.error("Invalid dataset: " + "; ".join(report["errors"][:10]))

        # LLM Training Advisor
        if args.llm_advisor and args.action == "train":
            _llm_training_advisor(report, args)

    model = YOLO(str(args.weights))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == "train":
        model.train(data=str(args.data.resolve()), epochs=args.epochs, imgsz=args.imgsz,
                    device=args.device, project=str(args.output.resolve()), name="road",
                    seed=42, deterministic=True)
    elif args.action == "evaluate":
        result = model.val(data=str(args.data.resolve()), split="test", device=args.device,
                           imgsz=args.imgsz, project=str(args.output.resolve()), name="evaluation")
        report = {"weights": str(args.weights), "split": "test", "metrics": result.results_dict,
                  "speed_ms": result.speed}
        (args.output / "evaluation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(model.export(format="onnx", imgsz=args.imgsz, device=args.device,
                           dynamic=False, simplify=False))


def quantize_model(onnx_path: Path, output_dir: Path) -> None:
    """INT8 dynamic quantization of an ONNX model for edge deployment."""
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType
    except ImportError as exc:
        raise SystemExit("onnxruntime is required for quantization: pip install onnxruntime") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    quantized = output_dir / f"{onnx_path.stem}_int8.onnx"
    print(f"Quantizing {onnx_path} -> {quantized} (INT8 dynamic)")
    quantize_dynamic(
        model_input=str(onnx_path),
        model_output=str(quantized),
        weight_type=QuantType.QInt8,
    )
    original = onnx_path.stat().st_size
    sized = quantized.stat().st_size
    print(f"Done. {original / 1024 / 1024:.1f} MB -> {sized / 1024 / 1024:.1f} MB "
          f"({sized / original * 100:.0f}% of original)")
    print(f"Run with: DETECTOR_RUNTIME=onnx MODEL_PATH={quantized}")


def _llm_training_advisor(report: dict, args) -> None:
    """Ask local LLM for training parameter suggestions."""
    import sys, os
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    from backend.llm import suggest_training_params

    splits = report.get("splits", {})
    num_images = sum(splits.values()) if isinstance(splits, dict) else 0
    num_classes = len(report.get("classes", []))

    print("\n" + "=" * 60)
    print("🤖 LLM 训练参数顾问 (Qwen2)")
    print("=" * 60)
    print(f"数据集: {num_images} 张图片, {num_classes} 个类别")
    print(f"分桶: {splits}")
    print(f"设备: {args.device}")
    print("-" * 60)

    suggestion = suggest_training_params(num_images, num_classes, splits, args.device)
    if suggestion is None:
        print("⚠ LLM 不可用,使用默认参数继续训练")
        print(f"  epochs={args.epochs}, imgsz={args.imgsz}, device={args.device}")
        print("=" * 60 + "\n")
        return

    print(f"推荐 epochs: {suggestion.get('recommended_epochs', args.epochs)}")
    print(f"推荐 batch:  {suggestion.get('recommended_batch', '?')}")
    print(f"推荐 imgsz:  {suggestion.get('recommended_imgsz', args.imgsz)}")
    print(f"建议: {suggestion.get('advice', '')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
