# 来源

工具的部署经验整理自本地 2026-11-08 ARM CPU 仿真实验，验证后端为 SAPIEN、Mesa Lavapipe 和 Open Image Denoise。

- `patches/sapien-3.0.2-cpu-build.patch` 是针对 SAPIEN 源码的两处本地修改；上游版权与 Apache-2.0 许可见 `patches/SAPIEN-LICENSE`。基线 commit 见 `docs-setup.md`。
- 本仓库不捆绑 SAPIEN、Mesa、OIDN、ISPC 或 TBB 二进制，也不包含 RobotWin/RMBench 资产。
- `examples/kunpeng-*.png` 是本工具自己构建的几何体场景渲染结果，不使用外部机器人 mesh。
