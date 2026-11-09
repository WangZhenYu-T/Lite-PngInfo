# Lite-PngInfo

A lightweight, local web UI for reading PNG metadata, organizing generation prompts and parameters, and saving favorite images in SQLite.

## 版本区别 / Version history

当前版本为 **v2**。v1 是最初的 NAI 元信息阅读与本地收藏版本；v2 增加多来源分类、原始字段浏览和明确的空状态。v3 收藏独立大图查看器、v4 Civitai 查询仍为计划功能。

| 能力 | v1 | v2（当前） |
|---|---|---|
| NAI 分类 | 顶层正负提示词与基础参数 | 保留原能力，增加角色提示词分区与来源模型信息 |
| A1111 / Forge | 能读到 parameters 文本，尚无专用分类 | 提取正负提示词、生成参数、已记录的 checkpoint / LoRA 及 hash |
| ComfyUI | 原始 prompt / workflow 字符串 | 简单且无歧义的路径可提取提示词；复杂图引导查看 JSON 或导入 ComfyUI，分类不猜测模型与采样参数 |
| JSON 浏览与复制 | 展示整理后的完整响应 | 任意文本字段格式化浏览、逐字段复制原文、导出有序字段集合 |
| 原文与精度 | 部分字段被原位解码，重复 key 被覆盖 | 保留重复文本条目、压缩/后置文本与原始字符串；大整数 seed 保持准确 |
| 无生成元信息 PNG | 可读取，但缺少专门的空状态展示 | 明确提示，保留预览、基本信息和收藏能力 |
| 收藏 | 保存原图与当时解析结果 | 增加来源标识；旧记录打开时重新解析，写回前备份，保留原图、ID 和创建时间 |
| 换图与重置 | 基础操作 | 失效旧结果，避免旧响应覆盖新图或重置状态 |
| 运行依赖 | Python + Pillow | 相同，无新增依赖或前端构建步骤 |

Current version: **v2**. v1 provided NAI extraction, normalized JSON output, and SQLite favorites. v2 adds source-specific classification, lossless original-text access, explicit empty states, and on-demand favorite upgrades. See [CHANGELOG.md](CHANGELOG.md) for change details.

### 从 v1 升级 / Upgrading from v1

1. 停止旧应用，更新代码后按原启动方式运行；依赖安装仍使用 `requirements.txt`。
2. 保留 `data/favorites.sqlite3`，无需手动改表。旧收藏首次打开时更新分类；更新前自动保存 `data/favorites.before-v2.sqlite3`。
3. v2 的 JSON 视图按原始字段组织，不再输出重复的 `raw` / `png_text`；分类 seed 用十进制字符串，原文字段的内容保持不变。
4. 备份包含旧收藏数据，解除收藏只修改当前数据库；不再需要备份时可自行删除备份文件。

## Features

- Drag and drop a PNG or choose one from the file picker.
- Automatically identify NAI, A1111, Forge, and ComfyUI metadata.
- Read NAI/A1111/Forge prompts and available settings, model names/hashes, and recorded LoRAs. NAI v4 character prompts keep their own sections.
- Keep ComfyUI's categorized view small: image details and prompts from a simple, unambiguous save/sampler/text path. Complex workflows remain available in JSON; drag the PNG into ComfyUI to use the workflow.
- Browse every text field with JSON formatting when possible, copy its original text, or export the ordered original field collection. Duplicate keys and compressed/post-image PNG text are preserved.
- Keep large integer seeds exact in categorized and formatted views and original copies.
- Read and favorite valid PNGs without generation metadata, with explicit empty states.
- Hide the image preview when desired.
- Clear the current image and in-memory session data with Reset.
- Save and remove favorites. Favorites include the original PNG, prompts, and complete parsed metadata.
- Keep favorite data locally in `data/favorites.sqlite3`.

## Requirements

- Python 3.10 or newer
- Pillow (installed with `requirements.txt`)

The web server uses Python's standard library. No Node.js, frontend build, or external service is required.

## Run on Linux or macOS

```sh
python3 -m pip install -r requirements.txt
./run.sh
```

Or run `python3 app.py` directly. Open <http://127.0.0.1:8765>.

## Run on Windows

Install Python 3.10 or newer, then from the project folder run:

```bat
py -m pip install -r requirements.txt
run-windows.bat
```

Open <http://127.0.0.1:8765>. The Python application itself works natively on Windows; WSL is not required. `run-windows.bat` is the portable native Windows launcher.

The Chinese-named `启动 PNGInfo*.bat` launchers are convenience scripts for the author's WSL distribution named `Ubuntu-D`; they are specific to that setup and are not needed for a native Windows installation.

## Configuration

The default address is `127.0.0.1:8765`, which avoids ComfyUI's common port `8188`. Configure the bind address and port with environment variables:

```sh
PNGINFO_HOST=127.0.0.1 PNGINFO_PORT=8765 python3 app.py
```

On Windows Command Prompt:

```bat
set PNGINFO_HOST=127.0.0.1
set PNGINFO_PORT=8765
python app.py
```

Only bind to a network interface you trust. This app is designed for local use and does not implement user authentication.

## Data and privacy

- Images are limited to 30 MB and must be valid PNG files.
- A read image is held in server memory for the current browser session until Reset or server shutdown.
- Images are written to the local SQLite database only when favorited.
- Removing a favorite deletes its stored image and metadata from the database.
- Runtime database files are ignored by Git and should not be committed.
- Opening a v1 favorite reparses its saved original PNG on demand. Before the first upgraded result is written, the app creates `data/favorites.before-v2.sqlite3` using SQLite backup. Original image bytes, favorite IDs, and creation dates are preserved. Old list items show “待更新分类” until opened.
- If an archived PNG cannot be reparsed, the archived result remains readable; it is not presented as original text. A database/backup write error leaves the old record intact and is reported for retry.
- The backup contains images and metadata as well. Removing a favorite changes the active database; it does not remove the record from that backup. Manage or remove your local backup separately when you no longer need it.

## Repository layout

```text
app.py                         Python HTTP server, sessions, and SQLite favorites
metadata.py                    PNG text reader and source-specific parsers
static/                        Browser UI assets
requirements.txt               Python dependencies
run.sh                         Linux/macOS launcher
run-windows.bat                Native Windows launcher
启动 PNGInfo*.bat               Optional WSL-specific launchers
```

## Development

Run the regression tests with:

```sh
python -m unittest discover -s tests -v
```

Tests generate small PNGs and use temporary databases and ephemeral ports. They do not modify your favorites or stop a running instance. CI runs the same tests on Windows and Ubuntu with Python 3.10 and 3.13.
