# Lite-PngInfo

[English](#english) | [简体中文](#简体中文)

## English

A lightweight local web application for reading PNG generation metadata and saving favorite images. **Current version: v2.** The interface is currently in Chinese; both English and Chinese usage instructions are provided below.

### Download

For **Windows 10/11 (64-bit)**, download **Lite-PngInfo-v2-Windows-x64.zip** from [Releases](https://github.com/WangZhenYu-T/Lite-PngInfo/releases). v1 is also available for users who need the original version.

1. Extract the **entire ZIP** into a writable folder, such as your Desktop.
2. Double-click **Lite-PngInfo.exe**. Your default browser opens automatically.
3. Choose/drop a PNG and click Read. Close the small launcher window to stop the app.

**No Python installation, dependency installation, terminal commands, account, or API key required.** Keep the `_internal` folder beside the executable. Do not launch from inside the ZIP. The portable folder stores favorites in `data/` beside the executable; moving that entire folder keeps your collection.

Download the named **Windows-x64.zip** attachment for this experience. GitHub's automatic “Source code” links are for developers and require the source setup below. The executable is unsigned; Windows may display a publisher/reputation warning. Verify downloads came from this repository's Release page. Linux/macOS currently use the source setup; no desktop binaries for those platforms are provided.

### Version comparison

| Capability | v1 | v2 |
|---|---|---|
| NAI | Main positive/negative prompts and basic settings | Also displays character prompts and available model information |
| A1111 / Forge | Raw parameters text | Categorized prompts, settings, recorded checkpoints, LoRAs, and hashes |
| ComfyUI | Raw prompt/workflow strings | Prompts from a simple, unambiguous save path; complex graphs remain in JSON |
| JSON | Complete normalized response | Formatted field browser, exact original-text copy, ordered field export |
| Text preservation | Duplicate keys overwritten; some values decoded in place | Duplicate, compressed, and post-image text preserved; large integer seeds stay exact |
| PNGs without generation data | Basic reading | Explicit empty state, image details, preview, and favorites |
| Favorites | Original PNG and archived parse result | Source labels; old records reparsed on demand with a backup before write-back |
| File changes/reset | Basic controls | Previous results invalidated; stale responses cannot overwrite a new result |
| Runtime dependencies | Python + Pillow | Unchanged |

ComfyUI classification intentionally does not list sampling settings, models, or LoRAs. Open JSON mode for stored fields, or drag the PNG into ComfyUI to import any embedded workflow. v3's independent favorite viewer and v4's Civitai lookup are not included. Details: [CHANGELOG.md](CHANGELOG.md).

### Windows source setup (developers)

Install Python 3.10 or newer, then run these commands inside the extracted folder:

```bat
py -3 -m pip install -r requirements.txt
run-windows.bat
```

If `py` is unavailable, use the explicit path to your Python interpreter, or `python` if it selects the intended installation:

```bat
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:8765>. Keep the terminal open while using the application; press Ctrl+C to stop it. Native Windows does not require WSL.

### Linux and macOS source setup

Use a virtual environment to keep dependencies local:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open <http://127.0.0.1:8765>. If your chosen Python already has Pillow installed, you may run `sh run.sh` instead. Using `sh` also works when extracting a ZIP does not preserve executable permissions. Keep the terminal open; press Ctrl+C to stop.

### Use and configuration

Choose or drop a PNG, click Read, and switch between categorized and JSON views. v2 offers original-text copy per field; the collection export preserves duplicate keys as ordered entries. Valid images without metadata can still be previewed and favorited. Reset clears the current session; it does not delete favorites.

The desktop Release opens its own local address automatically and uses a free port if 8765 is occupied. Its launcher has Open browser and Exit buttons. The following environment settings apply to source runs; the desktop Release always binds to localhost.

Source runs bind to `127.0.0.1:8765` by default. If the port is occupied, choose another port. Environment settings apply to the current terminal only.

Linux/macOS, with the virtual environment above:

```sh
PNGINFO_PORT=8766 .venv/bin/python app.py
```

Windows Command Prompt:

```bat
set PNGINFO_PORT=8766
py -3 app.py
```

`PNGINFO_HOST` changes the bind address. This application is intended for local use and has no user authentication; keep the default host unless you intentionally need trusted network access. URLs must use your selected port.

### Data and upgrading from v1

- Only valid PNGs up to 30 MB are accepted. Images are sent to the local application server, not a hosted image service. Reading does not require internet access after dependencies are installed.
- Favorites are saved in `data/favorites.sqlite3` **inside the application folder**, which must be writable. No personal database is bundled.
- To upgrade, stop v1 first. Keep a separate backup of its `data/` folder, extract v2 into a new folder, and copy the stopped application's `data/` folder there before starting v2. Avoid overwriting a newer database with an older one.
- Existing IDs, original PNG bytes, and creation dates are preserved. Old favorites initially show a pending source label; opening one reparses its saved PNG. Before the first write-back, SQLite creates `data/favorites.before-v2.sqlite3`.
- If reparse fails, the archived result remains readable. If the backup or write fails, the original record is retained and an error is shown.
- Removing a favorite deletes it from the active database, **not from an existing backup**. Backup files contain images and metadata; manage them separately.
- v2 changes the response structure: the duplicated `raw`/`png_text` objects are replaced by ordered entries, and categorized seeds use decimal strings. Original field text is preserved.
- Stop the application before copying, restoring, or moving its database. To return to v1, use a separate copy of the original v1 database.

### Source and validation

`app.py` contains the HTTP service and favorites; v2's `metadata.py` contains parsers; `static/` contains the UI; `tests/` contains generated fixtures and isolated tests. The desktop launcher is shared by both Release versions, without changing their version-specific parsers. Release archives identify the application and packaging commits in `VERSION.txt`, include dependency license notices and a per-file checksum manifest, and have a SHA-256 checksum attachment.

Run the tests with your chosen interpreter:

```sh
python -m unittest discover -s tests -v
```

Tests use temporary databases and ephemeral ports. CI covers Windows and Ubuntu with Python 3.10 and 3.13. macOS instructions use standard Python, but macOS is not currently part of the CI matrix.

---

## 简体中文

一个轻量的本地 PNG 生成元信息阅读与收藏工具。**当前版本为 v2。** 界面目前使用中文；本文上半部分为完整英文说明，下半部分为对应中文说明。

### 下载

**Windows 10/11（64 位）**用户请在 [Releases](https://github.com/WangZhenYu-T/Lite-PngInfo/releases) 下载 **Lite-PngInfo-v2-Windows-x64.zip**。需要最初版本的用户也可以下载 v1。

1. 将 **整个 ZIP 完整解压**到可写目录，例如桌面。
2. 双击 **Lite-PngInfo.exe**，默认浏览器会自动打开。
3. 选择或拖入 PNG，点击“读取”；关闭小启动窗口即可退出。

**无需安装 Python、依赖，无需命令行、账号或 API 密钥。** 请保留程序旁的 `_internal` 文件夹，不要直接在压缩包里运行。收藏保存在程序旁的 `data/` 中；移动时携带整个文件夹即可保留收藏。

普通用户请选择带 **Windows-x64.zip** 名称的附件。GitHub 自动生成的“Source code”供开发者使用，需要按后面的源码说明配置环境。程序尚未代码签名，Windows 可能提示发布者或信誉警告；请确认下载来源是本仓库的 Release 页面。Linux/macOS 目前通过源码运行，尚未提供这些平台的桌面二进制包。

### 版本区别

| 能力 | v1 | v2 |
|---|---|---|
| NAI | 顶层正负提示词与基础参数 | 增加角色提示词与可用模型信息 |
| A1111 / Forge | 原始 parameters 文本 | 分类提取提示词、参数、已记录的 checkpoint、LoRA 与哈希 |
| ComfyUI | 原始 prompt/workflow 字符串 | 简单且无歧义的保存路径可提取提示词，复杂图保留在 JSON |
| JSON | 整理后的完整响应 | 按字段格式化、准确复制原文、导出有序字段集合 |
| 文本保真 | 重复键被覆盖，部分字段被原位解码 | 保留重复、压缩和图像数据之后的文本，大整数 seed 不丢精度 |
| 无生成信息 PNG | 基础读取 | 明确空状态，保留基本信息、预览和收藏 |
| 收藏 | 原图和当时解析结果 | 来源标识，旧记录按需重新解析，写回前备份 |
| 换图与重置 | 基础操作 | 失效旧结果，旧响应不能覆盖新结果 |
| 运行依赖 | Python + Pillow | 保持不变 |

ComfyUI 分类模式按设计不列出采样参数、模型和 LoRA。请在 JSON 模式查看已保存字段，或将图片拖入 ComfyUI 导入内嵌工作流。v3 独立收藏查看器和 v4 Civitai 查询尚未包含。完整更新记录见 [CHANGELOG.md](CHANGELOG.md)。

### Windows 源码运行（开发者）

安装 Python 3.10 或更新版本，在解压目录中执行：

```bat
py -3 -m pip install -r requirements.txt
run-windows.bat
```

如果没有 `py`，使用 Python 解释器的完整路径，或在确认指向正确安装后使用 `python`：

```bat
python -m pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:8765>。使用时保持终端窗口开启，按 Ctrl+C 停止。原生 Windows 运行不需要 WSL。

### Linux 和 macOS 源码运行

推荐使用虚拟环境隔离依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

打开 <http://127.0.0.1:8765>。如果选用的 Python 已安装 Pillow，也可执行 `sh run.sh`；ZIP 解压未保留可执行权限时，同样可以使用 `sh`。保持终端开启，按 Ctrl+C 停止。

### 使用与配置

选择或拖入 PNG，点击“读取”，在分类和 JSON 模式间切换。v2 支持逐字段复制原文；导出字段集合时用有序条目保留重复键。无元信息的有效图片仍可预览和收藏。“重置”清空当前会话，不删除收藏。

桌面 Release 自动打开本机地址；8765 被占用时自动使用空闲端口，启动窗口提供“打开浏览器”和“退出”按钮。以下环境设置用于源码运行，桌面 Release 始终只监听本机。

源码默认地址为 `127.0.0.1:8765`。端口被占用时可以另选端口；环境设置仅作用于当前终端。

Linux/macOS，使用上面的虚拟环境：

```sh
PNGINFO_PORT=8766 .venv/bin/python app.py
```

Windows 命令提示符：

```bat
set PNGINFO_PORT=8766
py -3 app.py
```

`PNGINFO_HOST` 可以修改监听地址。应用面向本地使用，没有账号认证；除非确实需要可信网络访问，否则保留默认监听地址。访问网址时使用自己设置的端口。

### 数据与从 v1 升级

- 仅接受不超过 30 MB 的有效 PNG。图片发送到本机应用服务，不上传到托管图片服务；安装依赖后，读取图片无需联网。
- 收藏保存在**应用目录内**的 `data/favorites.sqlite3`，应用目录必须可写。下载包不携带个人数据库。
- 升级前先停止 v1，单独备份原有 `data/` 目录，将 v2 解压到新目录，把已停止应用的 `data/` 复制过去，再启动 v2。避免用旧数据库覆盖较新的收藏。
- 原收藏 ID、原始图片字节和创建时间保留。旧收藏最初显示待更新分类，打开后从原图重新解析；首次写回前自动创建 `data/favorites.before-v2.sqlite3`。
- 原图无法重新解析时仍可查看历史结果；备份或写回失败时保留原记录并显示错误。
- 解除收藏只删除当前数据库的记录，**不会删除已有备份中的内容**。备份包含图片和元信息，需单独管理。
- v2 响应结构使用有序条目代替重复的 `raw`/`png_text`，分类 seed 使用十进制字符串，原始字段文本保留。
- 复制、恢复或移动数据库前应停止应用。需要回到 v1 时，使用原 v1 数据库的独立副本。

### 源码与验证

`app.py` 为 HTTP 服务与收藏逻辑，v2 的 `metadata.py` 为解析器，`static/` 为界面，`tests/` 为合成样本与隔离测试。两个 Release 共用桌面启动器，但各自使用对应版本的解析代码。发行包通过 `VERSION.txt` 标明应用与打包提交，附带依赖许可、逐文件校验清单和独立 SHA-256 校验附件。

使用选定的解释器运行测试：

```sh
python -m unittest discover -s tests -v
```

测试使用临时数据库和临时端口。CI 覆盖 Windows、Ubuntu 及 Python 3.10、3.13。macOS 说明采用标准 Python 方式，但当前 CI 矩阵尚未包含 macOS。
