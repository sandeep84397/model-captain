import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


class CliTest(unittest.TestCase):
    def run_cli(self, *args, cwd):
        return subprocess.run([sys.executable, "-m", "model_guide", *args], cwd=cwd,
                              env=ENV, text=True, capture_output=True)

    def test_help_advertises_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli("--help", cwd=tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("evaluate", result.stdout)
        self.assertIn("recommend", result.stdout)

    def test_offline_workflow_and_init_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_cli("init", cwd=tmp).returncode, 0)
            self.assertNotEqual(self.run_cli("init", cwd=tmp).returncode, 0)
            run = self.run_cli("evaluate", "--provider", "demo", "--output", "run.json", cwd=tmp)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("synthetic", run.stdout)
            report = self.run_cli("report", "--input", "run.json", cwd=tmp)
            self.assertEqual(report.returncode, 0, report.stderr)
            self.assertIn("cost unknown", report.stdout)
            recommendation = self.run_cli("recommend", "--input", "run.json", "--category", "debugging", "--task", "fix", cwd=tmp)
            self.assertNotEqual(recommendation.returncode, 0)
            exported = self.run_cli("export", "--input", "run.json", "--format", "agents-md", "--output", "AGENTS.md", cwd=tmp)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            self.assertIn("DEMONSTRATION", Path(tmp, "AGENTS.md").read_text())
