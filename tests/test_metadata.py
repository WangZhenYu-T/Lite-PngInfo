"""Source adapters and text fidelity, using only generated/sanitized PNG data."""

import io
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metadata import normalize_metadata
from PIL import Image, PngImagePlugin


def png(fields=(), info=None):
    info = info or PngImagePlugin.PngInfo()
    for key, value in fields:
        info.add_itxt(key, value if isinstance(value, str) else json.dumps(value))
    output = io.BytesIO()
    with Image.new("RGB", (32, 48)) as image:
        image.save(output, format="PNG", pnginfo=info)
    return output.getvalue()


def simple_graph():
    return {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a landscape"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "blur"}},
        "3": {"class_type": "KSampler", "inputs": {"positive": ["1", 0], "negative": ["2", 0], "seed": 42}},
        "4": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
    }


class MetadataTests(unittest.TestCase):
    def inspect(self, fields=(), info=None):
        return normalize_metadata(png(fields, info), "sample.png")

    def test_text_chunks_duplicates_compression_and_after_idat(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("same", "first")
        info.add_text("same", "second", zip=True)
        info.add_itxt("unicode", "中文", zip=True)
        data = png(info=info)
        payload = b"after\0late text"
        chunk = b"tEXt" + payload
        data = data[:-12] + struct.pack(">I", len(payload)) + chunk + struct.pack(">I", zlib.crc32(chunk)) + data[-12:]
        result = normalize_metadata(data, "sample.png")
        self.assertEqual([(e["key"], e["text"]) for e in result["entries"]],
                         [("same", "first"), ("same", "second"), ("unicode", "中文"), ("after", "late text")])
        self.assertEqual([e["chunk"] for e in result["entries"]], ["tEXt", "zTXt", "iTXt", "tEXt"])

    def test_any_json_preserves_original_and_large_integer(self):
        text = '{ "seed": 9007199254740993, "payload": [null, true] }'
        result = self.inspect([("custom", text), ("empty", ""), ("object", "{}"), ("scalar", "null")])
        entry = result["entries"][0]
        self.assertEqual(entry["text"], text)
        self.assertIn("9007199254740993", entry["formatted"])
        self.assertNotIn("decoded", entry)
        self.assertEqual(result["entries"][1]["text"], "")
        self.assertEqual(result["entries"][3]["formatted"], "null")

    def test_invalid_json_does_not_hide_other_fields(self):
        result = self.inspect([("bad", "{broken"), ("good", {"value": 3})])
        self.assertEqual(result["entries"][0]["kind"], "invalid-json")
        self.assertEqual(result["entries"][1]["kind"], "json")
        self.assertEqual(result["status"], "unclassified")
        result = self.inspect([("large-float", '{"number": 1e999}')])
        self.assertEqual(result["entries"][0]["text"], '{"number": 1e999}')
        self.assertEqual(result["entries"][0]["kind"], "invalid-json")

    def test_empty_and_unknown_metadata(self):
        self.assertEqual(self.inspect()["status"], "empty")
        self.assertEqual(self.inspect([("author", "Someone")])["status"], "unclassified")
        result = self.inspect([("Comment", {"prompt": None, "uc": [], "seed": None})])
        self.assertEqual(result["prompts"]["prompt"], "")
        self.assertEqual(result["prompts"]["negative_prompt"], "")
        self.assertEqual(result["generation"], {})

    def test_nai_parameters_roles_and_seed_precision(self):
        comment = {"prompt": "scene", "uc": "blur", "seed": 9007199254740993, "steps": 28,
                   "v4_prompt": {"caption": {"char_captions": [{"char_caption": "red hair"}]}},
                   "v4_negative_prompt": {"caption": {"char_captions": [{"char_caption": "hat"}]}}}
        result = self.inspect([("Comment", comment), ("Software", "NovelAI"), ("Source", "NovelAI test")])
        self.assertEqual(result["source"]["label"], "NAI")
        self.assertEqual(result["generation"]["seed"], "9007199254740993")
        self.assertEqual(result["prompts"]["characters"], [{"prompt": "red hair", "negative_prompt": "hat"}])
        self.assertEqual(result["models"][0]["name"], "NovelAI test")
        self.assertFalse(result["notes"])

    def test_v1_wrapped_nai_comment(self):
        result = self.inspect([("Comment", json.dumps(json.dumps({"prompt": "wrapped", "uc": "blur"})))])
        self.assertEqual(result["prompts"]["prompt"], "wrapped")
        result = self.inspect([("Software", "NovelAI"), ("Comment", {"seed": 0, "steps": 20})])
        self.assertEqual(result["generation"]["seed"], "0")
        self.assertEqual(result["generation"]["steps"], 20)

    def test_webui_multiline_settings_loras_and_forge(self):
        text = ('Style: vivid, colorful\na scene <lora:style:0.7>\nNegative prompt: blur <lora:negative:1>\n'
                'Steps: 28, Sampler: Euler, CFG scale: 5, Seed: 9007199254740993, '
                'Model: example, Model hash: abc123def0, Lora hashes: "style: abc, other: def", '
                'Extra: {"a": [1, 2]}, Version: f2.0.1v1.10.1')
        result = self.inspect([("parameters", text)])
        self.assertEqual(result["source"]["label"], "Forge")
        self.assertTrue(result["prompts"]["prompt"].startswith("Style: vivid, colorful"))
        self.assertEqual(result["generation"]["Seed"], "9007199254740993")
        self.assertEqual(result["generation"]["Extra"], '{"a": [1, 2]}')
        self.assertEqual(result["loras"], [{"name": "style", "weight": "0.7", "hash": "abc"},
                                         {"name": "negative", "weight": "1", "hash": ""},
                                         {"name": "other", "weight": "", "hash": "def"}])
        self.assertEqual(result["entries"][0]["text"], text)

    def test_single_setting_and_quoted_commas(self):
        result = self.inspect([("parameters", 'a scene\nNegative prompt: blur\nSeed: 42')])
        self.assertEqual(result["generation"], {"Seed": "42"})
        result = self.inspect([("parameters", 'scene\nSteps: 2, Extra: "a\\\\", Seed: 42, Version: v1.9.3')])
        self.assertEqual(result["generation"]["Seed"], "42")
        self.assertEqual(result["source"]["label"], "A1111")
        result = self.inspect([("parameters", 'scene\nNegative prompt: blur\nSteps: 20,\nSeed: 42,\nVersion: v1.9.3')])
        self.assertEqual(result["prompts"]["negative_prompt"], "blur")
        self.assertEqual(result["generation"]["Steps"], "20")
        self.assertEqual(result["generation"]["Seed"], "42")

    def test_simple_comfy_prompts_only(self):
        result = self.inspect([("prompt", simple_graph()), ("workflow", {"nodes": []})])
        self.assertEqual(result["source"]["label"], "ComfyUI")
        self.assertEqual(result["prompts"]["prompt"], "a landscape")
        self.assertEqual(result["prompts"]["negative_prompt"], "blur")
        self.assertEqual(result["generation"], {})
        self.assertEqual(result["models"], [])
        self.assertEqual(result["loras"], [])

    def test_complex_comfy_is_not_guessed(self):
        for change in ("second-sampler", "second-save", "dynamic-text", "disabled"):
            with self.subTest(change=change):
                graph = simple_graph()
                if change == "second-sampler":
                    graph["6"] = {"class_type": "KSampler", "inputs": {}}
                elif change == "second-save":
                    graph["6"] = {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}}
                elif change == "dynamic-text":
                    graph["1"]["inputs"]["text"] = ["6", 0]
                else:
                    graph["5"]["mode"] = 2
                result = self.inspect([("prompt", graph)])
                self.assertEqual(result["prompts"]["prompt"], "")
                self.assertTrue(result["notes"])
        self.assertEqual(self.inspect([("workflow", {"nodes": []})])["prompts"]["prompt"], "")

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_metadata(b"not png", "sample.png")
        output = io.BytesIO()
        Image.new("RGB", (2, 2)).save(output, format="JPEG")
        with self.assertRaises(ValueError):
            normalize_metadata(output.getvalue(), "fake.png")

    def test_inventory_includes_inactive_editor_and_subgraph_models(self):
        workflow = {"nodes": [
            {"id": 1, "type": "CheckpointLoaderSimple", "widgets_values": ["a/base.safetensors"], "mode": 2},
            {"id": 2, "type": "LoraLoader", "widgets_values": ["style.safetensors", 0, 0], "mode": 4},
            {"id": 3, "type": "UNETLoader", "widgets_values": ["diffusion.safetensors", "default"]}],
            "definitions": {"subgraphs": [{"nodes": [
                {"id": 1, "type": "CheckpointLoader", "widgets_values": ["config.yaml", "b/base.safetensors"]}]}]}}
        graph = {"2": {"class_type": "LoraLoader", "inputs": {"lora_name": "style.safetensors",
                 "model_hash": "ABCDEF0123", "strength_model": 0.5}}}
        result = self.inspect([("prompt", graph), ("workflow", workflow)])
        self.assertEqual([v["name"] for v in result["models"]],
                         ["a/base.safetensors", "diffusion.safetensors", "b/base.safetensors"])
        self.assertEqual(len(result["loras"]), 1)
        self.assertEqual(result["loras"][0]["hash"], "ABCDEF0123")
        self.assertEqual(len(result["loras"][0]["origins"]), 2)
        self.assertTrue(any("不一定在启用状态" in n for n in result["notes"]))
        self.assertEqual(result["generation"], {})

    def test_inventory_conflicts_dynamic_and_unknown_nodes(self):
        graph = {"1": {"class_type": "LoraLoader", "inputs": {"lora_name": "same.safetensors", "hash": "11111111"}},
                 "2": {"class_type": "LoraLoader", "inputs": {"lora_name": "same.safetensors", "hash": "22222222"}}}
        workflow = {"nodes": [
            {"id": 3, "type": "LoraLoader", "widgets_values": ["same.safetensors"]},
            {"id": 4, "type": "LoraLoader", "inputs": [{"name": "lora_name", "link": 7}], "widgets_values": ["stale.safetensors"]},
            {"id": 5, "type": "CustomLoraLoader", "widgets_values": ["unknown.safetensors"]}]}
        result = self.inspect([("prompt", graph), ("workflow", workflow)])
        self.assertEqual({v["hash"] for v in result["loras"]}, {"11111111", "22222222", ""})
        self.assertNotIn("stale.safetensors", [v["name"] for v in result["loras"]])
        self.assertTrue(any("不同哈希" in n for n in result["notes"]))
        self.assertTrue(any("无法识别" in n for n in result["notes"]))

    def test_editor_explicit_named_model_hash(self):
        workflow = {"nodes": [{"id": 7, "type": "LoraLoaderModelOnly", "widgets_values": ["style.safetensors", 1],
                     "properties": {"models": [{"name": "style.safetensors", "hash": "a" * 64}]}}]}
        result = self.inspect([("workflow", workflow)])
        self.assertEqual(result["loras"][0]["hash"], "A" * 64)
        workflow["nodes"][0]["properties"]["models"][0]["name"] = "other.safetensors"
        self.assertEqual(self.inspect([("workflow", workflow)])["loras"][0]["hash"], "")


if __name__ == "__main__":
    unittest.main()
