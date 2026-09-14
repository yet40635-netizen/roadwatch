from typing import Literal

VisualLabel = Literal["water", "obstacle", "accident", "pothole", "oil", "garbage"]
VISUAL_LABELS = ["water", "obstacle", "accident", "pothole", "oil", "garbage"]
LABEL_NAMES = {"water": "积水", "obstacle": "道路障碍", "accident": "事故",
               "pothole": "坑洞", "oil": "油渍", "garbage": "垃圾杂物"}
