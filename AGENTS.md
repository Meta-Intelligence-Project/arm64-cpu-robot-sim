# Agent 使用说明

目的：判断 ARM Linux 上的 SAPIEN CPU 物理和软件光追是否可用，提供能人工查看的渲染图与机器可读结果。

1. 读取 `hardware.md` 和 `troubleshooting.md`。未知硬件标记为未验证，不自动当作受支持。
2. 询问或发现用户已有仿真 Python、Mesa prefix、SAPIEN native libs。不要猜测本机目录适用于其他机器。
3. 用 `scripts/configure.py` 在新目录生成 profile。它只写配置，不安装依赖。缺少原生依赖时读 `docs-setup.md`，清楚报告缺什么。
4. 先运行 `scripts/check_env.py`。再运行 `scripts/render_check.py`，给每次运行独立目录。资源紧张时先选 160×120、8 spp、3 帧、4 线程。
5. 检查返回码、`result.json` 和 `worker.log`。只有子进程正常退出才能报告成功；文件存在但进程崩溃仍是失败。
6. 打开输出 PNG，核对红/蓝/金属方块、地面、阴影。不要凭图像方差判断色彩或材质正确。
7. 用户需要去噪且已准备兼容 CPU OIDN 时再加 `--denoise`。明确 raw 和 denoised 的区别。
8. 发现新硬件结果时，经用户允许后新增验收记录；记录 CPU、系统、驱动、版本、参数、图片与退出状态。不要把一次场景测试写成整个 benchmark 已验证。

约束：
- 配置只影响子进程，不改 shell profile、系统 ICD、系统动态库或已有共享 runtime。
- 不自动关闭训练／仿真进程，不连接已有 policy server。该探针没有网络通信。
- 不静默退回 raster、不降低机器人 mesh、不修改成功判定来掩盖失败。
- 不把 `set_ray_tracing_denoiser('oidn')` 当作 CPU 降噪已执行的证据。
- 不把 OIDN 的 `--cpu=cortex-a57` 与 Lavapipe 的 `LP_NATIVE_VECTOR_WIDTH=256` 混为一谈：前者约束机器指令，后者是软件驱动代码生成配置。

开发验收：`python -m unittest discover -s tests -v`。真实渲染必须在可用 profile 上运行；单元测试通过不等于 native 后端通过。
