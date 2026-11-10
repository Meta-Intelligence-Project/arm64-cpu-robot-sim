"""Write an isolated launch profile for already-installed native dependencies."""

import json
from pathlib import Path

OIDN_LIBRARY = "libOpenImageDenoise.so"


def configure(python, mesa_prefix, output, library_dirs=(), oidn_prefix=None, threads=4):
    """Create ``output/profile.json`` and ``output/lvp.json``; return the profile path.

    Raises ValueError for invalid input. Nothing is installed or modified outside
    ``output``, which must not exist yet.
    """
    if not 1 <= threads <= 256:
        raise ValueError("threads must be 1..256")
    mesa_prefix = Path(mesa_prefix).resolve()
    driver = mesa_prefix / "lib" / "libvulkan_lvp.so"
    if not driver.is_file():
        raise ValueError(f"Missing Lavapipe driver: {driver}")
    python = Path(python)
    if not python.is_file():
        raise ValueError(f"Python executable missing: {python}")
    libs = [driver.parent, *(Path(d).resolve() for d in library_dirs)]
    oidn = None
    if oidn_prefix:
        oidn_prefix = Path(oidn_prefix).resolve()
        candidates = (oidn_prefix / sub / OIDN_LIBRARY for sub in ("lib64", "lib"))
        oidn = next((c for c in candidates if c.exists()), None)
        if oidn is None:
            raise ValueError(f"OIDN shared library missing under {oidn_prefix}")
        libs.insert(1, oidn.parent)
    missing = [str(d) for d in libs if not d.is_dir()]
    if missing:
        raise ValueError(f"Native library directory missing: {', '.join(missing)}")

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifests = sorted(mesa_prefix.glob("share/vulkan/icd.d/lvp*.json"))
    api = json.loads(manifests[0].read_text())["ICD"]["api_version"] if manifests else "1.3.0"
    icd = output / "lvp.json"
    icd_data = dict(
        file_format_version="1.0.1",
        ICD=dict(library_path=str(driver), api_version=api),
    )
    icd.write_text(json.dumps(icd_data, indent=2) + "\n")
    profile = dict(
        schema_version=1,
        # Keep the venv executable path; resolving the symlink would lose venv packages.
        python=str(python.absolute()),
        icd=str(icd),
        library_dirs=list(dict.fromkeys(map(str, libs))),
        threads=threads,
        vector_width=256,
    )
    if oidn:
        profile["oidn_library"] = str(oidn)
    path = output / "profile.json"
    path.write_text(json.dumps(profile, indent=2) + "\n")
    return path
