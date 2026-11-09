"""Build a versioned standalone app using only explicitly selected Git objects."""

import argparse
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["app.py", "requirements.txt", "static/app.js", "static/index.html", "static/style.css", "tests/test_app.py"]


def git(*args):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT)


def build(version, ref, output):
    sha = git("rev-parse", f"{ref}^{{commit}}").decode().strip()
    if platform.system() != "Windows":
        raise SystemExit("Desktop releases must be built on Windows")
    system = "Windows"
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Only x64 builds are configured")
    work = output / f"work-{version}-{system}"
    work.mkdir(parents=True, exist_ok=False)
    source = work / "source"
    source.mkdir()
    files = FILES + (["metadata.py", "tests/test_metadata.py"] if version == "v2" else [])
    for name in files:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git("show", f"{sha}:{name}"))
    (source / "desktop.py").write_bytes((ROOT / "scripts/desktop.py").read_bytes())
    # Test version-specific source before bundling. The launcher does not change its parsers.
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=source, check=True)
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "Lite-PngInfo",
            "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
            "--specpath", str(work), "--add-data", f"{source / 'static'}{os.pathsep}static"]
    if system == "Windows":
        args.append("--windowed")
    subprocess.run(args + [str(source / "desktop.py")], cwd=source, check=True)
    bundle = work / "dist/Lite-PngInfo"
    executable = bundle / ("Lite-PngInfo.exe" if system == "Windows" else "Lite-PngInfo")
    report = work / "smoke.json"
    subprocess.run([str(executable), "--smoke-test", str(report)], cwd=work, check=True, timeout=45)
    if json.loads(report.read_text())["ok"] is not True:
        raise SystemExit("Bundle smoke test failed")
    if (bundle / "data").exists():
        raise SystemExit("Smoke test wrote user data into the release folder")
    guide = release_readme(version, system)
    (bundle / "README.txt").write_text(guide, encoding="utf-8")
    packaging_sha = git("rev-parse", "HEAD").decode().strip()
    (bundle / "VERSION.txt").write_text(f"Lite-PngInfo {version}\nCode commit: {sha}\nPackaging commit: {packaging_sha}\nPlatform: {system} x64\nPython: {platform.python_version()}\nPillow: {importlib.metadata.version('Pillow')}\nPyInstaller: {importlib.metadata.version('PyInstaller')}\n", encoding="utf-8")
    licenses = bundle / "licenses"
    licenses.mkdir()
    for distribution in ("Pillow", "PyInstaller"):
        dist = importlib.metadata.distribution(distribution)
        for item in dist.files or []:
            if "license" in str(item).lower() and dist.locate_file(item).is_file():
                target = licenses / distribution / Path(str(item)).name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(dist.locate_file(item), target)
    for name in ("LICENSE.txt", "LICENSE"):
        candidate = Path(sys.base_prefix) / name
        if candidate.is_file():
            shutil.copyfile(candidate, licenses / "Python-LICENSE.txt")
            break
    manifest = []
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        manifest.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}")
    (bundle / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    name = f"Lite-PngInfo-{version}-{system}-x64"
    archive = output / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
            zipped.write(path, f"{name}/{path.relative_to(bundle).as_posix()}")
    (output / (archive.name + ".sha256")).write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
    if system == "Windows":
        extracted = work / "unpacked"
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(extracted)
        installed = extracted / name
        for line in (installed / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            if hashlib.sha256((installed / relative).read_bytes()).hexdigest() != digest:
                raise SystemExit(f"Extracted file checksum mismatch: {relative}")
        clean_env = {key: value for key, value in os.environ.items() if key not in ("PYTHONHOME", "PYTHONPATH")}
        clean_env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        subprocess.run([str(installed / "Lite-PngInfo.exe"), "--smoke-test", str(work / "unpacked-smoke.json")],
                       cwd=work, env=clean_env, check=True, timeout=45)
        if json.loads((work / "unpacked-smoke.json").read_text())["ok"] is not True:
            raise SystemExit("Extracted bundle smoke test failed")
        launcher_report = work / "launcher-smoke.json"
        # Exercise the normal GUI path, automatic browser launch, occupied-port handling and Exit.
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                occupied.bind(("127.0.0.1", 8765))
                occupied.listen()
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE and getattr(exc, "winerror", None) != 10048:
                    raise
                # An existing user instance already supplies the occupied-port condition.
            subprocess.run([str(installed / "Lite-PngInfo.exe"), "--launcher-test", str(launcher_report)],
                           cwd=work, env=clean_env, check=True, timeout=30)
        launcher_result = json.loads(launcher_report.read_text())
        if launcher_result["ok"] is not True or launcher_result["browser_url"].endswith(":8765"):
            raise SystemExit("Normal launcher/port fallback verification failed")
    print(f"Verified release: {archive}")


def release_readme(version, system):
    exe = "Lite-PngInfo.exe" if system == "Windows" else "Lite-PngInfo"
    capability = ("NAI prompts/settings, normalized JSON, local favorites." if version == "v1" else
                  "NAI/A1111/Forge metadata, minimal ComfyUI prompts, original JSON text, local favorites.")
    return f"""Lite-PngInfo {version} — {system} x64

ENGLISH
1. Extract the entire archive to a writable folder (for example, your Desktop).
2. Open {exe}. Your default browser opens automatically.
3. Choose/drop a PNG and click Read. The interface is in Chinese.
4. Close the small launcher window to stop the app.

No Python installation, dependency installation, terminal commands, account, or API key required.
Keep the _internal folder beside the executable. Do not run directly inside the ZIP.
Favorites are stored beside the program in data/favorites.sqlite3. Move the whole folder to keep them.
{capability}
This build is unsigned. It is a local HTTP app and binds only to 127.0.0.1.
If port 8765 is occupied it uses an available local port, shown in the launcher.
Read VERSION.txt for the source commit. MANIFEST.sha256 lists file checksums; licenses/ contains dependency notices.
For upgrades, close the old app first and back up data/. Copy data/ into the new app folder before opening it.
v2 reparses old favorites on demand and creates data/favorites.before-v2.sqlite3 before its first write-back.
Deleting a favorite does not remove it from old backups. Keep a separate v1 database copy if returning to v1.

简体中文
1. 完整解压到可写目录，例如桌面。
2. 双击 {exe}，默认浏览器自动打开。
3. 选择或拖入 PNG，点击“读取”。
4. 关闭小启动窗口即可停止应用。

无需安装 Python、依赖，无需命令行、账号或 API 密钥。
请保留程序旁的 _internal 文件夹；不要直接在压缩包中运行。
收藏位于程序旁的 data/favorites.sqlite3，移动时请携带整个文件夹。
本版{'提供 NAI 提示词和参数、整理后的 JSON、本地收藏。' if version == 'v1' else '提供 NAI/A1111/Forge 分类、ComfyUI 精简提示词、JSON 原文和本地收藏。'}
程序未做代码签名，仅监听本机 127.0.0.1；8765 被占用时自动选择可用端口，启动窗口会显示地址。
VERSION.txt 标明源码提交，MANIFEST.sha256 提供文件校验，licenses/ 保存依赖许可。
升级前先退出旧版并备份 data/，将 data/ 复制到新版程序旁，再启动新版。
v2 打开旧收藏时按需更新，首次写回前创建 data/favorites.before-v2.sqlite3。
解除收藏不会修改旧备份；回到 v1 请使用原 v1 数据库的独立副本。
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=("v1", "v2"), required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    build(args.version, args.ref, args.output)
