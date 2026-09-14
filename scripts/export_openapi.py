import json
from pathlib import Path

from backend.main import app
from inference.main import app as detector

ROOT = Path(__file__).resolve().parents[1]


def describe(schema):
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        return " / ".join(describe(item) for item in schema["anyOf"])
    if schema.get("type") == "array":
        return "array<" + describe(schema["items"]) + ">"
    return schema.get("type", "object") + (" (" + schema["format"] + ")" if "format" in schema else "")


def main():
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    lines = ["# 完整接口参考", "", (docs / "API-guide.md").read_text(encoding="utf-8")]
    for name, service in [("openapi.json", app), ("inference-openapi.json", detector)]:
        schema = service.openapi()
        (docs / name).write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        lines.extend(["", "## " + schema["info"]["title"], ""])
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                lines.extend([f"### {method.upper()} `{path}`", "", operation.get("summary", ""), ""])
                parameters = operation.get("parameters", [])
                if parameters:
                    lines.extend(["| 参数 | 位置 | 必填 | 类型与约束 |", "|---|---|---|---|"])
                    for parameter in parameters:
                        spec = json.dumps(parameter["schema"], ensure_ascii=False).replace("|", "\\|")
                        lines.append(f'| {parameter["name"]} | {parameter["in"]} | '
                                     f'{parameter.get("required", False)} | `{spec}` |')
                    lines.append("")
                for media, content in operation.get("requestBody", {}).get("content", {}).items():
                    lines.extend([f'请求体：`{media}` → **{describe(content["schema"])}**。', ""])
                for code, response in operation["responses"].items():
                    results = [describe(c["schema"]) for c in response.get("content", {}).values()]
                    lines.append(f'- `{code}`：{response["description"]}；' + ", ".join(results))
                lines.append("")
        lines.extend(["## " + schema["info"]["title"] + " 字段字典", ""])
        for name, model in schema["components"]["schemas"].items():
            lines.extend(["### " + name, "", "| 字段 | 必填 | 类型 | 约束 / 默认值 |", "|---|---|---|---|"])
            for field, value in model.get("properties", {}).items():
                constraints = {k: v for k, v in value.items()
                               if k not in {"title", "type", "$ref", "items", "anyOf"}}
                detail = json.dumps(constraints, ensure_ascii=False).replace("|", "\\|")
                lines.append(f'| {field} | {field in model.get("required", [])} | '
                             f'{describe(value)} | `{detail}` |')
            lines.append("")
    (docs / "API.md").write_text("\n".join(lines), encoding="utf-8")
    print("Exported API.md and both OpenAPI specifications")


if __name__ == "__main__":
    main()
