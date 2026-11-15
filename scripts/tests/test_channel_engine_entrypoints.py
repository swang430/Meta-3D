"""公开npm入口必须沿用安装者指定的计算库，不能覆盖成开发者本机路径。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ChannelEngineEntrypoints(unittest.TestCase):
    def test_schema_import_failure_is_nonzero_and_preserves_existing_file(self):
        source = Path(__file__).resolve().parents[2] / "scripts/export_channel_engine_schema.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "scripts/export_channel_engine_schema.py"
            script.parent.mkdir()
            script.write_text(source.read_text())
            output = root / "gui/src/types/channel-engine-schema.json"
            output.parent.mkdir(parents=True)
            output.write_text("previous schema")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            result = subprocess.run([sys.executable, str(script)], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), "previous schema")

    def test_entrypoints_preserve_configured_path(self):
        package = json.loads((Path(__file__).resolve().parents[2] / "package.json").read_text())
        for name in ("dev:channel-engine", "generate:schema"):
            with self.subTest(entrypoint=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "package.json").write_text(json.dumps({"scripts": package["scripts"]}))
                executable = root / "channel-engine-service/.venv/bin/python"
                executable.parent.mkdir(parents=True)
                executable.write_text('#!/bin/sh\nprintf "%s\\n" "$CHANNEL_ENGINE_PATH"\n')
                executable.chmod(0o755)
                supplied = str(root / "客户安装目录/ChannelEgine")
                result = subprocess.run(
                    ["npm", "run", "--silent", name], cwd=root,
                    env={**os.environ, "CHANNEL_ENGINE_PATH": supplied},
                    capture_output=True, text=True, check=True,
                )
                self.assertEqual(result.stdout.strip(), supplied)


if __name__ == "__main__":
    unittest.main()
