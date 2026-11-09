"""PNG text preservation and small, source-specific metadata adapters."""

from __future__ import annotations

import base64
import io
import json
import math
import re
import struct
import zlib
from typing import Any

from PIL import Image, PngImagePlugin, UnidentifiedImageError

SCHEMA_VERSION = 2
PARSER_VERSION = "2.0"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
        return str(value)
    return value


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the supported range")
    return number


def inflate_text(data: bytes) -> bytes:
    decoder = zlib.decompressobj()
    value = decoder.decompress(data, PngImagePlugin.MAX_TEXT_CHUNK + 1)
    if len(value) > PngImagePlugin.MAX_TEXT_CHUNK or decoder.unconsumed_tail:
        raise ValueError("PNG 压缩文本过大。")
    if not decoder.eof:
        raise ValueError("PNG 压缩文本不完整。")
    return value


def read_entries(data: bytes) -> list[dict[str, Any]]:
    """Read only PNG text chunks; Pillow handles image decoding and validation."""
    entries = []
    offset, total = 8, 0
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("PNG 数据块不完整。")
        if kind in (b"tEXt", b"zTXt", b"iTXt"):
            payload = data[offset + 8:end - 4]
            try:
                key, content = payload.split(b"\0", 1)
                if kind == b"zTXt":
                    if content[0] != 0:
                        raise ValueError("不支持的 PNG 文本压缩格式。")
                    content = inflate_text(content[1:])
                elif kind == b"iTXt":
                    flag, method = content[:2]
                    if flag not in (0, 1) or method != 0:
                        raise ValueError("不支持的 PNG 国际文本压缩格式。")
                    _, _, content = content[2:].split(b"\0", 2)
                    if flag:
                        content = inflate_text(content)
                total += len(content)
                if total > PngImagePlugin.MAX_TEXT_MEMORY:
                    raise ValueError("PNG 文本总量过大。")
                text = content.decode("utf-8" if kind == b"iTXt" else "latin-1")
            except (IndexError, UnicodeError, zlib.error) as exc:
                raise ValueError("无法读取 PNG 文本字段。") from exc
            entry = {"index": len(entries), "key": key.decode("latin-1"),
                     "chunk": kind.decode("ascii"), "text": text, "kind": "text"}
            try:
                decoded = json.loads(text, parse_constant=reject_constant, parse_float=finite_float)
            except (ValueError, RecursionError):
                if text.lstrip().startswith(("{", "[")):
                    entry["kind"] = "invalid-json"
            else:
                entry.update(kind="json", formatted=json.dumps(decoded, ensure_ascii=False, indent=2),
                             decoded=decoded)
            entries.append(entry)
        offset = end
        if kind == b"IEND":
            break
    return entries


def split_settings(text: str) -> list[str]:
    """Split commas outside quoted strings and brackets."""
    result, start, depth = [], 0, 0
    quoted, escaped = False, False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                result.append(text[start:index].strip())
                start = index + 1
    result.append(text[start:].strip())
    return result


def parse_parameters(text: str) -> tuple[str, str, dict[str, str]]:
    lines = text.splitlines()
    settings, boundary = {}, len(lines)
    # A settings block must start with a known parameter, never arbitrary prompt prose.
    candidates = [index for index, line in enumerate(lines) if line.startswith("Steps:")]
    candidates += [index for index in range(len(lines) - 1, -1, -1) if index not in candidates]
    for index in candidates:
        if re.match(r"^(Steps|Seed|Sampler|CFG scale|Size|Model hash|Model|Version):\s*", lines[index]):
            boundary = index
            for part in split_settings("\n".join(lines[index:])):
                key, separator, value = part.partition(":")
                if separator:
                    settings[key.strip()] = value.strip()
            break
    prompt_block = "\n".join(lines[:boundary])
    parts = re.split(r"(?m)^Negative prompt:\s?", prompt_block, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts) == 2 else "", settings


def webui_metadata(text: str, result: dict[str, Any]) -> None:
    positive, negative, settings = parse_parameters(text)
    version = settings.get("Version", "")
    forge = "forge" in version.lower() or bool(re.match(r"^f\d+\.\d+", version))
    result["source"] = {"family": "forge" if forge else "a1111",
                        "label": "Forge" if forge else ("A1111" if version.startswith("v") else "A1111-compatible")}
    result["prompts"].update(prompt=positive, negative_prompt=negative)
    result["generation"] = settings
    model, digest = settings.get("Model", ""), settings.get("Model hash", "")
    if model or digest:
        result["models"].append({"name": model, "hash": digest, "type": "Checkpoint"})
    loras = []
    for match in re.finditer(r"<lora:([^<>]+):([^:<>]+)>", positive + "\n" + negative, re.IGNORECASE):
        item = {"name": match[1], "weight": match[2], "hash": ""}
        if item not in loras:
            loras.append(item)
    hashes = settings.get("Lora hashes", "").strip('"')
    for part in hashes.split(","):
        name, separator, digest = part.rpartition(":")
        if not separator:
            continue
        name, digest = name.strip(), digest.strip()
        matching = [item for item in loras if item["name"] == name]
        if matching:
            for item in matching:
                item["hash"] = digest
        else:
            loras.append({"name": name, "weight": "", "hash": digest})
    result["loras"] = loras


def nai_metadata(fields: dict[str, Any], comment: dict[str, Any], result: dict[str, Any]) -> None:
    result["source"] = {"family": "nai", "label": "NAI"}
    prompts = result["prompts"]
    prompts["prompt"] = (text_value(comment.get("prompt")) or text_value(comment.get("positive_prompt"))
                         or text_value(fields.get("Description")))
    prompts["negative_prompt"] = text_value(comment.get("uc")) or text_value(comment.get("negative_prompt"))
    for key, target in (("v4_prompt", "prompt"), ("v4_negative_prompt", "negative_prompt")):
        value = comment.get(key)
        caption = value.get("caption") if isinstance(value, dict) else None
        if not isinstance(caption, dict):
            continue
        prompts[target] = prompts[target] or text_value(caption.get("base_caption"))
        roles = caption.get("char_captions", [])
        if isinstance(roles, list):
            for index, role in enumerate(roles):
                if isinstance(role, dict) and text_value(role.get("char_caption")):
                    while len(prompts["characters"]) <= index:
                        prompts["characters"].append({"prompt": "", "negative_prompt": ""})
                    prompts["characters"][index][target] = role["char_caption"]
    keys = ("seed", "steps", "scale", "cfg_rescale", "sampler", "noise_schedule", "width", "height",
            "n_samples", "request_type", "model_name", "model_hash", "version")
    result["generation"] = {key: str(comment[key]) if key == "seed" else comment[key]
                            for key in keys if isinstance(comment.get(key), (str, int, float, bool))}
    name = text_value(comment.get("model_name")) or text_value(fields.get("Source"))
    digest = text_value(comment.get("model_hash"))
    if name or digest:
        result["models"].append({"name": name, "hash": digest, "type": "NAI"})


def comfy_metadata(graph: Any, result: dict[str, Any]) -> None:
    result["source"] = {"family": "comfyui", "label": "ComfyUI"}
    result["notes"].append("完整工作流请选择 JSON 模式，或将图片直接拖入 ComfyUI。")
    if isinstance(graph, dict) and all(isinstance(n, dict) and isinstance(n.get("inputs"), dict) and not n.get("mode")
                                       for n in graph.values()):
        def linked(node: dict, key: str) -> dict:
            link = node.get("inputs", {}).get(key)
            if isinstance(link, list) and len(link) == 2 and link[1] == 0:
                return graph.get(str(link[0]), {})
            return {}

        saves = [n for n in graph.values() if n.get("class_type") in ("SaveImage", "SaveImageSimple")]
        samplers = [n for n in graph.values() if "Sampler" in text_value(n.get("class_type"))]
        if len(saves) == 1 and len(samplers) == 1:
            decoder = linked(saves[0], "images")
            sampler = linked(decoder, "samples")
            if decoder.get("class_type") == "VAEDecode" and sampler.get("class_type") == "KSampler":
                for key, target in (("positive", "prompt"), ("negative", "negative_prompt")):
                    encoder = linked(sampler, key)
                    if encoder.get("class_type") == "CLIPTextEncode":
                        result["prompts"][target] = text_value(encoder["inputs"].get("text"))
    if not result["prompts"]["prompt"] or not result["prompts"]["negative_prompt"]:
        result["notes"].append("无法可靠提取部分或全部本图提示词，请查看 JSON 或导入 ComfyUI。")


def normalize_metadata(image_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                raise ValueError("PNGInfo 只接受 PNG 图片。")
            image.load()
            entries = read_entries(image_bytes)
            text_keys = {entry["key"] for entry in entries}
            image_info = {key: json_safe(value) for key, value in image.info.items() if key not in text_keys}
            file_info = {"filename": filename, "format": "PNG", "mode": image.mode,
                         "width": image.width, "height": image.height,
                         "aspect_ratio": round(image.width / image.height, 6),
                         "file_size_bytes": len(image_bytes)}
    except (UnidentifiedImageError, OSError, EOFError, SyntaxError, struct.error, Image.DecompressionBombError) as exc:
        raise ValueError("无法读取该文件，请确认它是有效的 PNG 图片。") from exc

    fields = {entry["key"]: entry.get("decoded", entry["text"]) for entry in entries}
    result = {"schema_version": SCHEMA_VERSION, "parser_version": PARSER_VERSION,
              "file": file_info, "image_info": image_info, "entries": entries,
              "source": {"family": "unknown", "label": "来源未识别"},
              "prompts": {"prompt": "", "negative_prompt": "", "characters": []},
              "generation": {}, "models": [], "loras": [], "notes": []}
    comment = fields.get("Comment")
    comment_entry = next((entry for entry in reversed(entries) if entry["key"] == "Comment"), {})
    # v1 also accepted a Comment containing one JSON string wrapper.
    if comment_entry.get("kind") == "json" and isinstance(comment, str) and comment.lstrip().startswith("{"):
        try:
            comment = json.loads(comment, parse_constant=reject_constant, parse_float=finite_float)
        except (ValueError, RecursionError):
            pass
    if isinstance(comment, dict) and any(key in comment for key in ("prompt", "positive_prompt", "uc", "v4_prompt")):
        nai_metadata(fields, comment, result)
    elif (text_value(fields.get("Software")).lower() == "novelai"
          or text_value(fields.get("Source")).startswith("NovelAI")):
        nai_metadata(fields, comment if isinstance(comment, dict) else {}, result)
    elif isinstance(fields.get("parameters"), str):
        webui_metadata(fields["parameters"], result)
    elif (isinstance(fields.get("prompt"), dict) and any(
            isinstance(n, dict) and "class_type" in n for n in fields["prompt"].values())) or "workflow" in fields:
        comfy_metadata(fields.get("prompt"), result)
        if "workflow" not in fields:
            result["notes"].append("本图未记录 workflow 字段。")
    if result["source"]["family"] != "unknown":
        result["status"] = "recognized"
    elif any(entry["text"].strip() for entry in entries):
        result["status"] = "unclassified"
    else:
        result["status"] = "empty"
        result["source"] = {"family": "none", "label": "无生成元信息"}
    if any(entry["kind"] == "invalid-json" for entry in entries):
        result["notes"].append("部分字段不是有效 JSON，已保留原文。")
    # Only display strings cross the JSON boundary for arbitrary decoded payloads.
    for entry in entries:
        entry.pop("decoded", None)
    return json_safe(result)
