# Lite-PngInfo

A lightweight, local web UI for reading PNG metadata, organizing generation prompts and parameters, and saving favorite images in SQLite.

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

v2 is implemented locally. The independent favorite image viewer (v3) and Civitai lookup (v4) are planned. See [development notes](docs/DEVELOPMENT.md) and the [version iteration plan](docs/ROADMAP.md) for scope and validation details.
