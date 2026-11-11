"""Route Windows double-click startup without opening WSL SQLite through UNC."""

from pathlib import Path, PureWindowsPath
import argparse
import subprocess
import sys


def wsl_location(directory):
    path = PureWindowsPath(directory)
    anchor = path.anchor.strip("\\").split("\\")
    if len(anchor) == 2 and anchor[0].lower() in ("wsl.localhost", "wsl$"):
        return anchor[1], "/" + "/".join(path.parts[1:])
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--startup-test", metavar="REPORT")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    location = wsl_location(str(root))
    open_browser = options.open_browser
    if location:
        distro, directory = location
        args = ["wsl.exe", "--distribution", distro, "--exec", "python3",
                directory + "/scripts/wsl_launcher.py"]
        if open_browser:
            args.append("--open-browser")
        if options.startup_test:
            report = subprocess.check_output(["wsl.exe", "--distribution", distro, "--exec", "wslpath", "-u", options.startup_test], text=True).strip()
            args += ["--startup-test", report]
    else:
        if options.startup_test:
            args = [sys.executable, str(root / "scripts/desktop.py"), "--launcher-test", options.startup_test]
        else:
            args = [sys.executable, str(root / ("scripts/desktop.py" if open_browser else "app.py"))]
    return subprocess.call(args)


if __name__ == "__main__":
    sys.exit(main())
