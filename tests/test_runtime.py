import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from sapien_cpu_probe.cli import main
from sapien_cpu_probe.configure import configure
from sapien_cpu_probe.runtime import PACKAGE_DIR, environment, load_profile, run_worker


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class RuntimeTests(TempDirTest):
    def setUp(self):
        super().setUp()
        driver = self.root / "libvulkan_lvp.so"
        driver.touch()
        icd = self.root / "icd.json"
        icd.write_text(json.dumps({"ICD": {"library_path": str(driver)}}))
        self.profile = dict(schema_version=1, python=sys.executable, icd=str(icd),
                            library_dirs=[str(self.root)], threads=4, vector_width=256)

    def test_validate_and_reject_vector(self):
        p = self.root / "profile.json"
        p.write_text(json.dumps(self.profile))
        self.assertEqual(load_profile(p), self.profile)
        self.profile["vector_width"] = 128
        p.write_text(json.dumps(self.profile))
        with self.assertRaises(ValueError):
            load_profile(p)

    def test_child_env_isolated_without_parent_mutation(self):
        with patch.dict(os.environ, {"LD_PRELOAD": "wrongLLVM", "PYTHONPATH": "wrongRepo",
                                     "VK_DRIVER_FILES": "gpu"}):
            e = environment(self.profile, self.root)
            self.assertNotIn("LD_PRELOAD", e)
            self.assertNotIn("PYTHONPATH", e)
            self.assertEqual(e["VK_DRIVER_FILES"], self.profile["icd"])
            self.assertEqual(os.environ["LD_PRELOAD"], "wrongLLVM")
            self.assertEqual(e["LP_NATIVE_VECTOR_WIDTH"], "256")

    def test_worker_pythonpath_is_staged_copy_only(self):
        out = self.root / "run"
        child = MagicMock()
        child.wait.return_value = 1
        with patch("sapien_cpu_probe.runtime.subprocess.Popen", return_value=child) as popen:
            run_worker(self.profile, out, "check", {}, 2)
        path = popen.call_args.kwargs["env"]["PYTHONPATH"]
        self.assertEqual(Path(path), out.resolve() / "pkg")
        self.assertEqual(sorted(p.name for p in Path(path).iterdir()), [PACKAGE_DIR.name])
        self.assertNotIn(str(PACKAGE_DIR.parent), path.split(os.pathsep))

    def test_real_child_imports_staged_worker(self):
        # No SAPIEN here (or no Vulkan): the worker must still start and report failure.
        r = run_worker(self.profile, self.root / "run", "check", {}, 60)
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("No module named 'sapien_cpu_probe'", Path(r["log"]).read_text())
        self.assertTrue((self.root / "run" / "worker-result.json").exists())

    def test_completed_result_but_native_exit_crash_is_failure(self):
        out = self.root / "run"

        def spawn(*args, **kw):
            (out / "worker-result.json").write_text('{"status":"passed"}')
            child = MagicMock()
            child.wait.return_value = -11
            return child

        with patch("sapien_cpu_probe.runtime.subprocess.Popen", side_effect=spawn):
            r = run_worker(self.profile, out, "render", {}, 2)
        self.assertEqual(r["status"], "failed")
        self.assertEqual(r["signal"], "SIGSEGV")

    def test_timeout_terminates_own_process_group(self):
        child = MagicMock()
        child.pid = 123456
        child.wait.side_effect = [subprocess.TimeoutExpired("test", 1), -15]
        with patch("sapien_cpu_probe.runtime.subprocess.Popen", return_value=child), \
                patch("sapien_cpu_probe.runtime.os.killpg") as kill:
            r = run_worker(self.profile, self.root / "run", "check", {}, 1)
        kill.assert_called_once_with(123456, signal.SIGTERM)
        self.assertTrue(r["timed_out"])
        self.assertEqual(r["status"], "failed")

    def test_output_never_overwrites(self):
        with self.assertRaises(FileExistsError):
            run_worker(self.profile, self.root, "check", {}, 1)

    def test_missing_result_is_not_success(self):
        child = MagicMock()
        child.wait.return_value = 0
        with patch("sapien_cpu_probe.runtime.subprocess.Popen", return_value=child):
            r = run_worker(self.profile, self.root / "run", "check", {}, 1)
        self.assertEqual(r["status"], "failed")


class FakeNativeTree(TempDirTest):
    def setUp(self):
        super().setUp()
        self.mesa = self.root / "mesa"
        (self.mesa / "lib").mkdir(parents=True)
        (self.mesa / "lib" / "libvulkan_lvp.so").touch()
        self.oidn = self.root / "oidn"
        (self.oidn / "lib64").mkdir(parents=True)
        (self.oidn / "lib64" / "libOpenImageDenoise.so").touch()


class ConfigureTests(FakeNativeTree):
    def test_profile_round_trips_through_load_profile(self):
        path = configure(sys.executable, self.mesa, self.root / "cfg", oidn_prefix=self.oidn)
        profile = load_profile(path)
        self.assertEqual(profile["python"], str(Path(sys.executable).absolute()))
        self.assertEqual(profile["library_dirs"],
                         [str(self.mesa.resolve() / "lib"), str(self.oidn.resolve() / "lib64")])
        self.assertTrue(profile["oidn_library"].endswith("libOpenImageDenoise.so"))

    def test_missing_driver_rejected_without_creating_output(self):
        with self.assertRaises(ValueError):
            configure(sys.executable, self.root / "nowhere", self.root / "cfg")
        self.assertFalse((self.root / "cfg").exists())

    def test_existing_output_rejected(self):
        with self.assertRaises(FileExistsError):
            configure(sys.executable, self.mesa, self.root)


class CliTests(FakeNativeTree):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as exit_info:
            main(list(argv))
        return exit_info.exception.code, json.loads(buf.getvalue())

    def test_configure_then_budget_error(self):
        code, result = self.run_cli("configure", "--python", sys.executable,
                                    "--mesa-prefix", str(self.mesa), "--output", str(self.root / "cfg"))
        self.assertEqual((code, result["status"]), (0, "configured"))
        code, result = self.run_cli("render", "--profile", result["profile"],
                                    "--output", str(self.root / "run"), "--spp", "4096")
        self.assertEqual(code, 2)
        self.assertIn("spp<=1024", result["error"])
        self.assertFalse((self.root / "run").exists())

    def test_denoise_requires_oidn(self):
        _, result = self.run_cli("configure", "--python", sys.executable,
                                 "--mesa-prefix", str(self.mesa), "--output", str(self.root / "cfg"))
        code, result = self.run_cli("render", "--profile", result["profile"],
                                    "--output", str(self.root / "run"), "--denoise")
        self.assertEqual(code, 2)
        self.assertIn("oidn_library", result["error"])


if __name__ == "__main__":
    unittest.main()
