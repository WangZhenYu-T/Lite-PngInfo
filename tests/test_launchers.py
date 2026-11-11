import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("windows_launcher", ROOT / "scripts/windows_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_wsl_unc_paths_are_routed_to_native_filesystem(self):
        for directory in (r"\\wsl.localhost\Ubuntu-D\home\user1\pnginfo",
                          r"\\wsl$\Ubuntu-D\home\user1\pnginfo"):
            self.assertEqual(launcher.wsl_location(directory), ("Ubuntu-D", "/home/user1/pnginfo"))
        self.assertIsNone(launcher.wsl_location(r"C:\Users\Example\BunnyInfo"))
        self.assertIsNone(launcher.wsl_location(r"\\server\share\BunnyInfo"))
