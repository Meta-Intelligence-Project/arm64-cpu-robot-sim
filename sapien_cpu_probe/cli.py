import argparse
import json
from pathlib import Path

from .configure import configure
from .runtime import load_profile, run_worker

LIMITS = dict(width=2048, height=2048, frames=100, spp=1024, depth=32)


def positive(value):
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sapien-cpu-probe",
        description="SAPIEN CPU physics + Lavapipe ray-tracing checks; JSON result on stdout",
    )
    sub = parser.add_subparsers(dest="operation", required=True)

    cfg = sub.add_parser("configure", help="Write a profile for existing native dependencies")
    cfg.add_argument("--python", required=True, type=Path, help="Simulation Python executable")
    cfg.add_argument("--mesa-prefix", required=True, type=Path)
    cfg.add_argument("--library-dir", action="append", type=Path, default=[])
    cfg.add_argument("--oidn-prefix", type=Path)
    cfg.add_argument("--threads", type=positive, default=4)
    cfg.add_argument("--output", required=True, type=Path, help="New profile directory")

    for name, text in (("check", "Check Vulkan device and ray-tracing capability"),
                       ("render", "Render a small physics scene with CPU ray tracing")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--profile", required=True, type=Path)
        p.add_argument("--output", required=True, type=Path,
                       help="Fresh output directory; never overwritten")
        p.add_argument("--timeout", type=positive, default=180)
        if name == "render":
            p.add_argument("--width", type=positive, default=320)
            p.add_argument("--height", type=positive, default=240)
            p.add_argument("--frames", type=positive, default=3)
            p.add_argument("--spp", type=positive, default=8)
            p.add_argument("--depth", type=positive, default=8)
            p.add_argument("--denoise", action="store_true",
                           help="Separate CPU OIDN pass on HDR buffers")
    return parser


def _probe(args):
    options = {}
    if args.operation == "render":
        over = [f"{k}<={v}" for k, v in LIMITS.items() if getattr(args, k) > v]
        if over:
            raise ValueError("Probe budget exceeded: " + ", ".join(over))
        options = {k: getattr(args, k) for k in (*LIMITS, "denoise")}
    profile = load_profile(args.profile)
    if options.get("denoise") and not Path(profile.get("oidn_library", "")).is_file():
        raise ValueError("--denoise requires an existing oidn_library in the profile")
    return run_worker(profile, args.output, args.operation, options, args.timeout)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "configure":
            path = configure(args.python, args.mesa_prefix, args.output,
                             args.library_dir, args.oidn_prefix, args.threads)
            result = dict(status="configured", profile=str(path),
                          note="Native dependencies were not installed or modified")
        else:
            result = _probe(args)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps(dict(status="failed", error=str(exc)), ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] in ("passed", "configured") else 1)
