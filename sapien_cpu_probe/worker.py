"""Runs only inside a disposable child configured before importing SAPIEN."""

import gc
import json
import os
import platform
import re
import resource
import subprocess
import sys
import time
import traceback
from pathlib import Path

STEPS_PER_FRAME = 15
SCENE_BOXES = (
    # name, position, RGBA, metallic
    ("red_dynamic", [0, -0.18, 0.5], [0.8, 0.04, 0.02, 1], 0),
    ("blue_static", [0.15, 0.2, 0.12], [0.02, 0.12, 0.8, 1], 0),
    ("silver_static", [0.35, -0.1, 0.12], [0.8, 0.8, 0.8, 1], 1),
)


def _cpu_model():
    model = platform.processor()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    try:
        raw = subprocess.run(["lscpu", "-J"], capture_output=True, text=True, timeout=5,
                             check=True, env={**os.environ, "LC_ALL": "C"})
        rows = json.loads(raw.stdout)["lscpu"]
        model = next((r["data"] for r in rows if r["field"] == "Model name:"), model)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        pass
    return model


def _versions():
    import importlib.metadata as md

    import sapien

    versions = {}
    for name in ("sapien", "numpy", "Pillow"):
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = getattr(sapien, "__version__", "unknown") if name == "sapien" else "unknown"
    return versions


def check(profile):
    import sapien

    summary = str(sapien.render.get_device_summary())
    software = "llvmpipe" in summary.lower() or "lavapipe" in summary.lower()
    rt = bool(re.search(r"rayTrace:\s*1", summary))
    info = dict(
        architecture=platform.machine(),
        cpu_model=_cpu_model(),
        platform=platform.platform(),
        python=sys.version.split()[0],
        versions=_versions(),
        device_summary=summary,
        software_vulkan=software,
        ray_tracing_advertised=rt,
        vector_width=os.environ.get("LP_NATIVE_VECTOR_WIDTH"),
        threads=profile.get("threads", 4),
        oidn_library=profile.get("oidn_library"),
        note="Capability check only; run render to verify BLAS construction and readback",
    )
    if not software or not rt:
        raise RuntimeError("Required software Vulkan ray-tracing capability missing: " + summary)
    return info


def _gamma(x):
    import numpy as np

    return np.clip(np.maximum(x[..., :3], 0) ** (1 / 2.2), 0, 1)


def render(output, options, profile):
    import numpy as np
    import sapien
    from PIL import Image

    sapien.render.set_camera_shader_dir("rt")
    sapien.render.set_ray_tracing_samples_per_pixel(options["spp"])
    sapien.render.set_ray_tracing_path_depth(options["depth"])
    sapien.render.set_ray_tracing_denoiser("none")
    scene = sapien.Scene([sapien.physx.PhysxCpuSystem(), sapien.render.RenderSystem(device="cpu")])
    scene.set_timestep(1 / 250)
    scene.set_ambient_light([0.25, 0.25, 0.25])
    scene.add_ground(0)
    scene.add_directional_light([1, 0, -1], [2, 2, 2], shadow=True)
    actors = []
    for name, position, color, metallic in SCENE_BOXES:
        material = sapien.render.RenderMaterial(
            base_color=color, metallic=metallic, roughness=0.15 if metallic else 0.6)
        builder = scene.create_actor_builder()
        builder.add_box_collision(half_size=[0.1, 0.1, 0.1])
        builder.add_box_visual(half_size=[0.1, 0.1, 0.1], material=material)
        actor = builder.build(name=name) if name == "red_dynamic" else builder.build_static(name=name)
        actor.set_pose(sapien.Pose(position))
        actors.append(actor)
    camera = scene.add_camera("probe", options["width"], options["height"], 1.0, 0.01, 10)
    camera.set_pose(sapien.Pose([-1.4, 0, 0.6], [0.99144486, 0, 0.13052619, 0]))
    initial = np.array(actors[0].pose.p, copy=True)

    timings, buffers, images = [], {}, []
    for frame in range(options["frames"]):
        start = time.monotonic()
        for _ in range(STEPS_PER_FRAME):
            scene.step()
        scene.update_render()
        camera.take_picture()
        buffers = {name: np.array(camera.get_picture(name), copy=True)
                   for name in ("Color", "HdrColor", "Albedo", "Normal")}
        for name, a in buffers.items():
            if a.shape[:2] != (options["height"], options["width"]) or not np.isfinite(a).all():
                raise ValueError(f"Invalid {name} render buffer")
        rgb = buffers["Color"][..., :3]
        if float(rgb.std()) < 0.01 or float(rgb.max()) < 0.05:
            raise ValueError("Image is blank or nearly constant")
        target = output / f"frame-{frame:03d}.png"
        Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(target)
        images.append(str(target))
        timings.append(time.monotonic() - start)

    final = np.array(actors[0].pose.p, copy=True)
    if not np.isfinite(final).all() or final[2] >= initial[2] - 0.001 or final[2] < 0:
        raise ValueError("Dynamic cube did not fall with a valid position")
    np.savez_compressed(output / "buffers.npz", **buffers)
    result = dict(
        shader="rt",
        physics="PhysxCpuSystem",
        renderer_device="cpu",
        spp=options["spp"],
        path_depth=options["depth"],
        resolution=[options["width"], options["height"]],
        physics_steps=STEPS_PER_FRAME * options["frames"],
        initial_cube_position=initial.tolist(),
        final_cube_position=final.tolist(),
        frame_seconds=timings,
        images=images,
        buffer_file=str(output / "buffers.npz"),
        denoiser="none",
        image_std=float(rgb.std()),
    )
    if options["denoise"]:
        from .oidn import denoise

        start = time.monotonic()
        hdr = denoise(profile["oidn_library"], buffers, profile.get("threads", 4))
        error = float(np.abs(_gamma(buffers["HdrColor"]) - buffers["Color"][..., :3]).max())
        if error > 1e-4:
            raise ValueError(f"Unexpected SAPIEN tonemapping: max error {error}")
        image = output / "denoised.png"
        Image.fromarray((_gamma(hdr) * 255).astype(np.uint8)).save(image)
        np.save(output / "denoised-hdr.npy", hdr)
        result.update(
            denoiser="OIDN CPU, RT HDR filter, separate readback pass",
            denoise_seconds=time.monotonic() - start,
            tonemap_max_error=error,
            denoised_image=str(image),
        )
    # Clean exit is part of acceptance; the parent checks the actual process exit.
    del camera, actor, builder, material, actors, scene
    gc.collect()
    return result


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output = Path(sys.argv[1])
    request = json.loads((output / "request.json").read_text())
    try:
        info = check(request["profile"])
        if request["operation"] == "render":
            info["render"] = render(output, request["options"], request["profile"])
            info["note"] = "Actual CPU physics, RT readback and cleanup executed; parent verifies process exit"
        result = dict(status="passed", **info)
    except Exception as exc:
        traceback.print_exc()
        result = dict(status="failed", error=str(exc))
    (output / "worker-result.json").write_text(json.dumps(result, indent=2) + "\n")
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
