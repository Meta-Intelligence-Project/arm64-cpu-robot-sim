# sapien-cpu-probe

给 code agent 用的 SAPIEN 纯 CPU 仿真环境探针（ARM Linux）。将 SAPIEN CPU PhysX、Mesa Lavapipe 软件光追和 CPU OIDN 的部署经验整理成可执行检查。

**已在鲲鹏 920 / Linux aarch64 上验证。** 不需要 NVIDIA GPU；有 NPU 的主机也不使用 NPU 做渲染。其他 ARM 硬件目前没有验收记录。

## 快速使用

本仓库不需要安装即可运行。控制脚本只依赖 Python 标准库；被启动的仿真 Python 环境需要已有的 **SAPIEN 3.0.2 CPU 构建、NumPy、Pillow**，以及支持光追的 **Mesa Lavapipe**。可选 CPU OIDN 用于降噪。

先告诉工具现有依赖在哪里。所有生成文件只放到新目录，不修改系统库或现有 Python 环境：

```bash
python scripts/configure.py \
  --python /path/to/sim-venv/bin/python \
  --mesa-prefix /path/to/mesa-env \
  --library-dir /path/to/sapien-native/lib64 \
  --oidn-prefix /path/to/oidn-cpu \
  --threads 4 \
  --output .local/my-machine

python scripts/check_env.py \
  --profile .local/my-machine/profile.json \
  --output runs/check-001

python scripts/render_check.py \
  --profile .local/my-machine/profile.json \
  --output runs/render-001 --denoise
```

没有 OIDN 时，去掉 `--oidn-prefix` 和 `--denoise` 即可验证原始光追。`configure` **只生成配置，不下载或编译原生依赖**；准备新机器请看 [环境准备](docs-setup.md)。

也可 `pip install --no-deps .`，然后使用 `sapien-cpu-probe configure|check|render ...`，参数与上面的脚本相同；模块入口为 `python -m sapien_cpu_probe`。控制端只需要标准库，可以和仿真 Python 不是同一个环境：worker 运行前会把本包复制到输出目录的 `pkg/`，子进程只导入这份拷贝。

## 验证什么

固定小场景包括红色动态方块、蓝色方块、金属方块、地面和阴影；不下载机器人资产。默认 320×240、8 spp、path depth 8、3 帧，每帧之间步进 15 次物理仿真。

- 强制 `RenderSystem(device='cpu')` 和 `PhysxCpuSystem()`，不回退到 GPU 或 raster。
- 检查软件 Vulkan 设备和光追能力；实际创建场景、构建加速结构并回读图像。
- 检查图像有限值、非空白、尺寸，以及动态方块发生下落。
- 可选：读取 HDR/albedo/normal，运行独立 CPU OIDN，再做 gamma tonemap。
- 检查子进程最终退出码，捕获 native crash、超时和退出时的析构崩溃。

输出：`result.json`、`worker.log`、`frame-000.png` 等图像、`buffers.npz`；启用降噪时还有 `denoised.png` 和 `denoised-hdr.npy`。**非空图像检查不代替视觉检查**，agent 应打开图片核对颜色、物体和阴影。

stdout 最终是一条 JSON：`status`、`exit_code`、`timed_out`、`output`、`log`、`details`。成功退出 0，验证失败退出 1，参数／配置错误退出 2。输出目录必须是新目录，禁止静默覆盖。

首次 shader/JIT/场景构建可能慢于后续帧。默认超时 180 秒；必要时显式使用 `--timeout 300`。worker 日志保留原始原生库输出。

## 给 agent 的入口

先读 [AGENTS.md](AGENTS.md)，然后读 [hardware.md](hardware.md) 和 [troubleshooting.md](troubleshooting.md)。检查进程中的驱动和动态库顺序，不要以 `import sapien` 成功代替渲染成功。

[RobotWin / RMBench 接入说明](examples/robotwin-rmbench.md) 解释如何使用相同环境，并区分渲染、规划和策略推理。本工具不包含机器人资产、CuRobo 替代实现或策略模型。

本次实际验证输出见 [examples/kunpeng-validation.json](examples/kunpeng-validation.json)，示例图片见 [examples/kunpeng-denoised.png](examples/kunpeng-denoised.png)。
