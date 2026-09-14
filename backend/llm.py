"""LLM client for Qwen2 via Ollama (OpenAI-compatible API).

Provides:
- chat(): generic LLM call with system+user messages
- analyze_event(): generate AI analysis for traffic events
- suggest_training_params(): suggest YOLO hyperparameters based on dataset
- suggest_annotation_strategy(): generate labeling guidance for datasets

All calls have a 90s timeout and graceful fallback to None on failure.
"""
import json
import logging
import urllib.error
import urllib.request

from backend.config import settings

logger = logging.getLogger(__name__)
_TIMEOUT = 90

# Candidate OpenAI-compatible paths. Standard first, Open WebUI second.
_CHAT_PATHS = ("/v1/chat/completions", "/api/v1/chat/completions")


def _post(path: str, payload: dict) -> tuple[bool, str | None]:
    """POST JSON and return (is_endpoint_error, content)."""
    url = f"{settings.llm_base_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return False, data["choices"][0]["message"].get("content")
    except urllib.error.HTTPError as exc:
        # 403/404/405 on this path means the endpoint is mounted elsewhere.
        if exc.code in (403, 404, 405):
            return True, None
        detail = exc.read().decode()[:300]
        logger.warning("LLM HTTP %s at %s: %s", exc.code, path, detail)
        return False, None
    except Exception as exc:
        logger.warning("LLM call failed at %s: %s", path, exc)
        return False, None


def _call(messages: list[dict], temperature: float = 0.7, max_tokens: int = 2048) -> str | None:
    """Call the OpenAI-compatible chat endpoint, trying known path variants.

    Qwen3 thinking models consume tokens on the reasoning trace before the
    visible answer, so max_tokens defaults high and thinking is disabled when
    the backend supports ``chat_template_kwargs.enable_thinking``.
    """
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for path in _CHAT_PATHS:
        _endpoint_error, content = _post(path, payload)
        if content and content.strip():
            return content.strip()
    return None


def _call_ollama_raw(prompt: str, system: str = "") -> str | None:
    """Fallback: call Ollama's native /api/chat endpoint (no OpenAI wrapper)."""
    url = f"{settings.llm_base_url.rstrip('/')}/api/chat"
    payload_obj = {
        "model": settings.llm_model,
        "stream": False,
        "options": {"temperature": 0.7},
        "messages": [],
    }
    if system:
        payload_obj["messages"].append({"role": "system", "content": system})
    payload_obj["messages"].append({"role": "user", "content": prompt})
    payload = json.dumps(payload_obj).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning("Ollama raw call failed: %s", exc)
        return None


def chat(prompt: str, system: str = "", temperature: float = 0.7) -> str | None:
    """Generic chat call. Tries OpenAI-compatible first, then Ollama native."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    result = _call(messages, temperature=temperature)
    if result:
        return result
    return _call_ollama_raw(prompt, system)


# ---------------------------------------------------------------------------
# Event AI Analysis
# ---------------------------------------------------------------------------

_EVENT_SYSTEM = (
    "你是道路智能交通分析助手。根据事件信息生成简洁的中文分析报告，"
    "包含：1.事态判断（一句话）2.可能原因（1-2条）3.处置建议（2-3条可操作的措施）。"
    "总字数控制在150字以内。"
)

def analyze_event(kind: str, severity: str, reason: str, source_name: str = "") -> str | None:
    """Generate AI analysis when a traffic event is created."""
    prompt = (
        f"交通事件类型: {kind}\n"
        f"严重程度: {severity}\n"
        f"监测点: {source_name or '未知'}\n"
        f"检测依据: {reason}\n"
        "请生成分析和处置建议。"
    )
    return chat(prompt, _EVENT_SYSTEM, temperature=0.3)


# ---------------------------------------------------------------------------
# Training Parameter Advisor
# ---------------------------------------------------------------------------

_TRAIN_SYSTEM = (
    "你是YOLO目标检测训练专家。根据数据集情况推荐训练超参数。"
    "只返回JSON格式，不要额外文字。格式："
    '{"recommended_epochs": N, "recommended_batch": N, "recommended_imgsz": N, '
    '"advice": "一句话建议"}'
)

def suggest_training_params(num_images: int, num_classes: int, splits: dict, device: str = "cpu") -> dict | None:
    """Suggest YOLO training hyperparameters based on dataset characteristics."""
    prompt = (
        f"数据集图片总数: {num_images}\n"
        f"类别数: {num_classes}\n"
        f"分桶: train={splits.get('train', 0)}, val={splits.get('val', 0)}, test={splits.get('test', 0)}\n"
        f"训练设备: {device}\n"
        "请推荐 epochs、batch size、imgsz，并给一句话建议。"
    )
    raw = chat(prompt, _TRAIN_SYSTEM, temperature=0.2)
    if not raw:
        return None
    # Extract JSON from response
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM training params: %s", raw)
        return None


# ---------------------------------------------------------------------------
# Annotation Strategy Assistant
# ---------------------------------------------------------------------------

_ANNOTATE_SYSTEM = (
    "你是数据标注专家，擅长道路场景目标检测标注。"
    "根据类别和图片信息，给出标注策略建议，包括："
    "1.各类别标注要点 2.容易混淆的类别区分方法 3.边界框标注规范。"
    "总字数200字以内。"
)

def suggest_annotation_strategy(categories: list[str], num_images: int) -> str | None:
    """Generate labeling guidance for a dataset."""
    prompt = (
        f"需要标注的目标类别: {', '.join(categories)}\n"
        f"数据集图片数量: {num_images}\n"
        "请给出标注策略建议。"
    )
    return chat(prompt, _ANNOTATE_SYSTEM, temperature=0.4)
