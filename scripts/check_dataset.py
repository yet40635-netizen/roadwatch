import argparse
import hashlib
import json
import math
from pathlib import Path

LABELS = ["water", "obstacle", "accident", "pothole", "oil", "garbage"]


def check_dataset(root):
    errors, counts, seen = [], {}, {}
    for split in ("train", "val", "test"):
        images = sorted((root / "images" / split).glob("*.jpg"))
        counts[split] = len(images)
        if not images:
            errors.append(f"{split}: no JPEG images")
        for image in images:
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            if digest in seen and seen[digest] != split:
                errors.append(f"{image.name}: identical image appears in {seen[digest]} and {split}")
            seen[digest] = split
            label = root / "labels" / split / f"{image.stem}.txt"
            if not label.exists():
                errors.append(f"{image.name}: missing label file")
                continue
            for number, line in enumerate(label.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    parts = line.split()
                    if len(parts) != 5 or not parts[0].isdigit():
                        raise ValueError
                    category = int(parts[0])
                    x, y, w, h = map(float, parts[1:])
                    if not 0 <= category < len(LABELS):
                        raise ValueError
                    if not all(math.isfinite(v) for v in (x, y, w, h)):
                        raise ValueError
                    if not (0 < w <= 1 and 0 < h <= 1 and w / 2 <= x <= 1 - w / 2
                            and h / 2 <= y <= 1 - h / 2):
                        raise ValueError
                except ValueError:
                    errors.append(f"{label.name}:{number}: invalid YOLO box")
    return {"images": counts, "errors": errors, "valid": not errors}


def main():
    parser = argparse.ArgumentParser(description="Validate an extracted RoadWatch YOLO dataset")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = check_dataset(args.directory)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
