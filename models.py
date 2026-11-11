"""Static inventory of known ComfyUI model references; never execute workflow nodes."""

import re

# name input, display category, widget position. Only stable, known layouts belong here.
LOADERS = {
    "CheckpointLoaderSimple": ("ckpt_name", "Checkpoint", 0),
    "CheckpointLoader": ("ckpt_name", "Checkpoint", 1),
    "LoraLoader": ("lora_name", "LoRA", 0),
    "LoraLoaderModelOnly": ("lora_name", "LoRA", 0),
    "UNETLoader": ("unet_name", "扩散模型", 0),
    "UnetLoaderGGUF": ("unet_name", "扩散模型", 0),
}
HASH_KEYS = ("sha256", "SHA256", "model_hash", "lora_hash", "hash")


def normalize_hash(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value.upper() if re.fullmatch(r"[0-9a-fA-F]{8,64}", value) else ""


def node_hash(values):
    for key in HASH_KEYS:
        digest = normalize_hash(values.get(key))
        if digest:
            return digest
    hashes = values.get("hashes")
    if isinstance(hashes, dict):
        for key in ("SHA256", "sha256", "AutoV2", "AutoV1", "BLAKE3", "CRC32"):
            digest = normalize_hash(hashes.get(key))
            if digest:
                return digest
    return ""


def comfy_inventory(graph, workflow, notes):
    found = []
    incomplete = False

    def add(node, node_id, location, editor=False):
        nonlocal incomplete
        kind = node.get("type" if editor else "class_type", "")
        if not isinstance(kind, str):
            incomplete = True
            return
        if kind not in LOADERS:
            if kind not in ("CLIPLoader", "DualCLIPLoader", "TripleCLIPLoader", "VAELoader", "UpscaleModelLoader") and any(word in kind.lower() for word in ("loader", "lora", "checkpoint")):
                incomplete = True
            return
        key, category, position = LOADERS[kind]
        inputs = node.get("inputs", {})
        name = inputs.get(key) if isinstance(inputs, dict) else None
        if editor and isinstance(name, list):
            incomplete = True
            return
        if editor and isinstance(inputs, list):
            named = next((v for v in inputs if isinstance(v, dict) and v.get("name") == key), None)
            if named and named.get("link") is not None:
                incomplete = True
                return
        widgets = node.get("widgets_values")
        if editor and not isinstance(name, str):
            if isinstance(widgets, dict):
                name = widgets.get(key)
            elif isinstance(widgets, list) and len(widgets) > position:
                name = widgets[position]
        if not isinstance(name, str) or not name.strip():
            incomplete = True
            return
        values = inputs if isinstance(inputs, dict) else {}
        digest = node_hash(values)
        properties = node.get("properties", {})
        records = properties.get("models", []) if isinstance(properties, dict) else []
        recorded_hashes = {node_hash(record) for record in records if isinstance(record, dict)
                           and record.get("name") == name and node_hash(record)} if isinstance(records, list) else set()
        origin = {"location": location, "node_id": str(node_id), "node_type": kind}
        if editor:
            origin["mode"] = node.get("mode", 0)
        strengths = {k: v for k, v in values.items() if k in ("strength_model", "strength_clip")
                     and isinstance(v, (str, int, float)) and not isinstance(v, bool)}
        if strengths:
            origin["strengths"] = strengths
        digests = recorded_hashes | ({digest} if digest else set())
        for value in sorted(digests) or [""]:
            found.append({"name": name.strip(), "hash": value, "type": category, "origins": [origin]})

    if isinstance(graph, dict):
        for node_id, node in graph.items():
            if isinstance(node, dict):
                add(node, node_id, "prompt")

    # An explicit stack also covers serialized subgraph definitions without recursive graph execution.
    stack = [(workflow, "workflow")]
    while stack:
        document, location = stack.pop()
        if not isinstance(document, dict):
            continue
        nodes = document.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    add(node, node.get("id", "?"), location, editor=True)
        definitions = document.get("definitions", {})
        subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
        if isinstance(subgraphs, list):
            for index, subgraph in enumerate(subgraphs):
                stack.append((subgraph, f"{location}/subgraph:{index}"))

    # An editor node can inherit a hash only from the corresponding runtime node, not a name alone.
    for item in found:
        if not item["hash"]:
            origin = item["origins"][0]
            hashes = {v["hash"] for v in found if v["type"] == item["type"] and v["name"] == item["name"] and v["hash"]
                      and origin["location"] == "workflow" and v["origins"][0]["location"] == "prompt"
                      and v["origins"][0]["node_id"] == origin["node_id"]}
            if len(hashes) == 1:
                item["hash"] = next(iter(hashes))
    items = {}
    for item in found:
        key = (item["type"], item["name"], item["hash"])
        if key in items:
            items[key]["origins"].extend(item["origins"])
        else:
            items[key] = item
    identities = {}
    for item in found:
        identities.setdefault((item["type"], item["name"]), set()).add(item["hash"])
    if any(len(hashes - {""}) > 1 for hashes in identities.values()):
        notes.append("同名模型存在不同哈希，已分开保留，请在 ComfyUI 中确认。")
    if incomplete:
        notes.append("部分模型节点或动态文件名无法识别，请在 JSON / ComfyUI 中确认完整列表。")
    return list(items.values())
