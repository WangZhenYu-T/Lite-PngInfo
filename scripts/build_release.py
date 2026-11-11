"""Build and verify a clean Windows desktop distribution from a Git ref."""

import argparse
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["app.py", "metadata.py", "models.py", "civitai.py", "requirements.txt", "static/app.js", "static/index.html",
         "static/style.css", "static/favicon.ico", "tests/test_app.py", "tests/test_metadata.py",
         "tests/test_civitai.py", "tests/test_launchers.py", "scripts/windows_launcher.py"]


def git(*args):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT)


def build(version, ref, output, working_tree=False):
    if not re.fullmatch(r"v\d+(?:\.\d+){0,2}(?:-[a-zA-Z0-9.]+)?", version):
        raise ValueError("Expected a version such as v2 or v2.1")
    sha = git("rev-parse", f"{ref}^{{commit}}").decode().strip()
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Desktop releases must be built on Windows x64")
    work = output / f"work-{version}-Windows"
    work.mkdir(parents=True, exist_ok=False)
    source = work / "source"
    source.mkdir()
    # Working-tree mode makes review builds possible without staging or committing user work.
    # It is never used by the publishing workflow and is marked prominently in VERSION.txt.
    def contents(name):
        return (ROOT / name).read_bytes() if working_tree else git("show", f"{sha}:{name}")
    for name in FILES + ["scripts/desktop.py"]:
        path = source / ("desktop.py" if name == "scripts/desktop.py" else name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents(name))
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=source, check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
                    "--name", "BunnyInfo", "--icon", str(source / "static/favicon.ico"),
                    "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
                    "--specpath", str(work), "--add-data", f"{source / 'static'}{os.pathsep}static",
                    str(source / "desktop.py")], cwd=source, check=True)
    bundle = work / "dist/BunnyInfo"
    executable = bundle / "BunnyInfo.exe"
    report = work / "smoke.json"
    subprocess.run([str(executable), "--smoke-test", str(report)], cwd=work, check=True, timeout=45)
    if json.loads(report.read_text())["ok"] is not True or (bundle / "data").exists():
        raise SystemExit("Bundle smoke test failed or created user data inside the bundle")
    (bundle / "README.txt").write_text(release_readme(version), encoding="utf-8")
    label = "LOCAL REVIEW BUILD — unpublished working tree" if working_tree else "Git source"
    (bundle / "VERSION.txt").write_text(
        f"BunnyInfo {version}\nBuild: {label}\nBase commit: {sha}\nPlatform: Windows x64\n"
        f"Python: {platform.python_version()}\nPillow: {importlib.metadata.version('Pillow')}\n"
        f"PyInstaller: {importlib.metadata.version('PyInstaller')}\n", encoding="utf-8")
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
    manifest = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}"
                for path in sorted(p for p in bundle.rglob("*") if p.is_file())]
    (bundle / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    name = f"BunnyInfo-{version}-Windows-x64"
    archive = output / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
            zipped.write(path, f"{name}/{path.relative_to(bundle).as_posix()}")
    (output / (archive.name + ".sha256")).write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
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
    subprocess.run([str(installed / "BunnyInfo.exe"), "--smoke-test", str(work / "unpacked-smoke.json")],
                   cwd=work, env=clean_env, check=True, timeout=45)
    if json.loads((work / "unpacked-smoke.json").read_text())["ok"] is not True:
        raise SystemExit("Extracted bundle smoke test failed")
    launcher_report = work / "launcher-smoke.json"
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            occupied.bind(("127.0.0.1", 8765))
            occupied.listen()
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE and getattr(exc, "winerror", None) != 10048:
                raise
        subprocess.run([str(installed / "BunnyInfo.exe"), "--launcher-test", str(launcher_report)],
                       cwd=work, env=clean_env, check=True, timeout=30)
    launcher_result = json.loads(launcher_report.read_text())
    if launcher_result["ok"] is not True or launcher_result["browser_url"].endswith(":8765"):
        raise SystemExit("Normal launcher/port fallback verification failed")
    print(f"Verified {'review build' if working_tree else 'release'}: {archive}")


def release_readme(version):
    return f"""BunnyInfo {version} — Windows x64

简体中文
1. 完整解压到可写目录，例如桌面。
2. 双击 BunnyInfo.exe，默认浏览器自动打开。
3. 选择或拖入 PNG，点击“读取”。关闭小启动窗口即可退出。

无需安装 Python、依赖，无需命令行、账号或 API 密钥。
请保留 _internal 文件夹，不要直接在 ZIP 中运行。
收藏位于程序旁的 data/favorites.sqlite3，移动时携带 data/。
仅监听本机；8765 被占用时自动选择空闲端口。
升级前退出旧版，备份并复制 data/ 到新版程序旁。旧收藏升级前生成数据库备份。
解除收藏只修改活动数据库，不修改旧备份；回退旧版请使用原数据库的独立副本。
程序未代码签名，Windows 可能显示未知发布者。
VERSION.txt 记录版本来源，MANIFEST.sha256 提供逐文件校验，licenses/ 保存依赖许可。

ENGLISH
1. Extract the entire ZIP to a writable folder.
2. Open BunnyInfo.exe; your browser opens automatically.
3. Choose/drop a PNG and click Read. Close the launcher to exit.

No Python, dependency installation, terminal commands, account or API key required.
Keep _internal beside the executable. Do not run inside the ZIP. The UI is Chinese.
Favorites are in data/favorites.sqlite3 beside the program. Move data/ with your app.
Localhost only; an available port is selected if 8765 is occupied.
Close the old app, back up data/, and copy it to the new folder before upgrading.
Old favorites are backed up before upgrading; deleting a favorite does not change old backups.
Use a separate original database copy when reverting to an older version.
This build is unsigned; Windows may report an unknown publisher.
See VERSION.txt, MANIFEST.sha256 and licenses/ for source, checksums and dependency notices.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--working-tree", action="store_true", help="Local unpublished review build only")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    build(args.version, args.ref, args.output, args.working_tree)
