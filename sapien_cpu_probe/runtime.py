"""Child-only Vulkan environment; no global environment or installation changes."""

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

# Variables that could pull in a foreign LLVM, Python install, GPU ICD or Vulkan layer.
_SCRUBBED_VARIABLES = (
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONPATH",
    "VK_ADD_DRIVER_FILES",
    "VK_LAYER_PATH",
    "VK_INSTANCE_LAYERS",
    "VK_LOADER_DRIVERS_SELECT",
    "VK_LOADER_DRIVERS_DISABLE",
)


def load_profile(path):
    profile = json.loads(Path(path).read_text())
    if profile.get("schema_version") != 1:
        raise ValueError("Expected profile schema_version=1")
    missing = [key for key in ("python", "icd") if key not in profile]
    if missing:
        raise ValueError(f"Profile is missing required keys: {', '.join(missing)}")
    for key in ("python", "icd"):
        p = Path(profile[key])
        if not p.is_absolute() or not p.is_file():
            raise ValueError(f"{key} must point to an existing absolute file: {p}")
    if not os.access(profile["python"], os.X_OK):
        raise ValueError("Profile Python is not executable")
    for p in profile.get("library_dirs", []):
        if not Path(p).is_absolute() or not Path(p).is_dir():
            raise ValueError(f"Invalid library directory: {p}")
    icd = json.loads(Path(profile["icd"]).read_text())
    library = Path(icd["ICD"]["library_path"])
    if library.is_absolute() and not library.is_file():
        raise ValueError(f"ICD refers to missing driver: {library}")
    threads = profile.get("threads", 4)
    if not isinstance(threads, int) or not 1 <= threads <= 256:
        raise ValueError("threads must be 1..256")
    if profile.get("vector_width", 256) != 256:
        raise ValueError("Verified ARM ray-tracing profile requires vector_width=256")
    return profile


def environment(profile, output):
    """Return a child environment dict for the profile; the current process is untouched.

    The inherited PYTHONPATH is removed. Callers that need extra import paths must add
    them explicitly.
    """
    env = os.environ.copy()
    for key in _SCRUBBED_VARIABLES:
        env.pop(key, None)
    env.update(
        VK_ICD_FILENAMES=profile["icd"],
        VK_DRIVER_FILES=profile["icd"],
        LD_LIBRARY_PATH=os.pathsep.join(profile.get("library_dirs", [])),
        LP_NATIVE_VECTOR_WIDTH=str(profile.get("vector_width", 256)),
        LP_NUM_THREADS=str(profile.get("threads", 4)),
        # Keep OpenMP users (NumPy BLAS, etc.) from competing with Lavapipe threads.
        OMP_NUM_THREADS="2",
        TORCH_DEVICE_BACKEND_AUTOLOAD="0",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        XDG_CACHE_HOME=str(Path(output) / "cache"),
    )
    return env


def _stage_package(output):
    """Copy this package into the run directory so the child imports only it.

    Pointing PYTHONPATH at the parent of PACKAGE_DIR would expose the controller's
    whole site-packages to the simulation Python when the tool is pip-installed.
    """
    staged = output / "pkg"
    shutil.copytree(
        PACKAGE_DIR,
        staged / PACKAGE_DIR.name,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return staged


def run_worker(profile, output, operation, options, timeout):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "cache").mkdir()
    request = dict(operation=operation, options=options, profile=profile)
    (output / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    env = environment(profile, output)
    env["PYTHONPATH"] = str(_stage_package(output))
    cmd = [profile["python"], "-m", f"{PACKAGE_DIR.name}.worker", str(output)]
    timed_out = False
    with (output / "worker.log").open("w") as log:
        child = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=output,
            start_new_session=True,
        )
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                code = child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                code = child.wait()
    result_file = output / "worker-result.json"
    try:
        details = json.loads(result_file.read_text()) if result_file.exists() else {}
    except (ValueError, OSError):
        details = {"error": "Worker result is unreadable"}
    passed = code == 0 and details.get("status") == "passed" and not timed_out
    result = dict(
        status="passed" if passed else "failed",
        operation=operation,
        exit_code=code,
        timed_out=timed_out,
        output=str(output),
        log=str(output / "worker.log"),
        details=details,
    )
    if code < 0:
        result["signal"] = signal.Signals(-code).name
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
