#!/usr/bin/env python3
"""Run `sapien-cpu-probe check` from a checkout without installing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sapien_cpu_probe.cli import main  # noqa: E402

main(["check", *sys.argv[1:]])
