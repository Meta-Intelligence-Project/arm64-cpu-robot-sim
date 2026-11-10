# 接入 RoboTwin / RMBench

sapien-cpu-probe 只验证底层的物理和渲染链路，不包含机器人资产、运动规划器或策略模型。本文说明怎样把同一套 CPU 环境用在 RoboTwin 或 RMBench 的任务上。

## 场景配置

SAPIEN 的场景要改用 CPU 物理和 CPU 渲染：

```python
import sapien

sapien.render.set_camera_shader_dir("rt")
sapien.render.set_ray_tracing_samples_per_pixel(32)
sapien.render.set_ray_tracing_path_depth(8)
sapien.render.set_ray_tracing_denoiser("none")  # 内置 OIDN 在 CPU 上不生效

scene = sapien.Scene([
    sapien.physx.PhysxCpuSystem(),
    sapien.render.RenderSystem(device="cpu"),
])
```

## 启动任务进程

Vulkan 驱动和动态库路径必须在 `import sapien` **之前**设置好，所以要在新的子进程里运行任务。`environment()` 根据配置文件生成子进程的环境变量，不会修改当前进程：

```python
import subprocess
from pathlib import Path

from sapien_cpu_probe.runtime import environment, load_profile

profile = load_profile(".local/my-machine/profile.json")
output = Path("runs/task-001").resolve()
(output / "cache").mkdir(parents=True)

subprocess.run(
    [profile["python"], "/path/to/your_task.py"],
    env=environment(profile, output),
    cwd="/path/to/benchmark-checkout",
    check=True,
)
```

`environment()` 会清掉继承来的 `PYTHONPATH`。如果任务需要额外的导入路径，请自己往返回的字典里加。

## 需要修改的地方

RoboTwin 和 RMBench 原本假定有 NVIDIA GPU，下面几处需要改：

| 环节 | 改法 |
|---|---|
| 物理 / 渲染设备 | 换成 `PhysxCpuSystem` 和 `RenderSystem(device="cpu")`。相机、mesh、材质、灯光和采样参数保持不变 |
| 降噪 | 内置 denoiser 设为 `none`，读回 HDR / Albedo / Normal 后调用 CPU OIDN，参考 `sapien_cpu_probe/oidn.py` |
| 运动规划 | CuRobo 需要 CUDA。生成 expert 数据时要换成 CPU 规划器，例如 MPlib，并记下规划行为和原来有哪些不同 |
| 策略推理 | 和渲染无关，需要单独确认能否在 CPU 或 NPU 上运行 |

渲染、运动规划、策略推理是三个独立的环节。渲染能在 CPU 上跑通，不代表另外两个也可以。

## RoboTwin 2.0 补丁

[patches/robotwin-2eeec322-cpu.patch](../patches/robotwin-2eeec322-cpu.patch) 是 RoboTwin 2.0 在 commit `2eeec322` 上的 CPU 移植，已经实际跑通。它改了 5 个文件：

| 文件 | 改动 |
|---|---|
| `envs/_base_task.py` | 场景改用 CPU PhysX 和 CPU 渲染。光追参数默认沿用官方设置（32 spp，深度 8），内置 denoiser 设为 `none` |
| `envs/camera/camera.py` | 可选开启 CPU OIDN 降噪；可选跳过策略用不到的相机；去掉顶层的 open3d 导入（aarch64 上缺 libgfortran） |
| `envs/robot/cpu_planner.py` | 新增，基于 MPlib 的 CPU 规划器，替代 CuRobo |
| `envs/robot/robot.py` | 两只手臂都改用上面的规划器 |
| `envs/utils/save_file.py` | 只在保存点云时才导入 open3d |

```bash
git clone https://github.com/RoboTwin-Platform/RoboTwin.git && cd RoboTwin
git checkout 2eeec322
git apply /path/to/sapien-cpu-probe/patches/robotwin-2eeec322-cpu.patch
```

可以通过下面这些环境变量调整行为：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ROBOTWIN_CPU_SHADER` | `rt` | 相机 shader，`rt` 表示光追 |
| `ROBOTWIN_CPU_SPP` / `ROBOTWIN_CPU_PATH_DEPTH` | 32 / 8 | 光追采样数和光路深度 |
| `ROBOTWIN_CPU_OIDN` | `0` | 设为 `1` 开启 CPU OIDN 降噪，库路径用 `ROBOTWIN_CPU_OIDN_LIBRARY` 指定 |
| `ROBOTWIN_CPU_OIDN_THREADS` | 8 | OIDN 线程数 |
| `ROBOTWIN_CPU_STATIC_CAMERAS` | 全部渲染 | 只渲染列出的固定相机，例如 `head_camera` |

除了 sapien-cpu-probe 的环境，仿真进程还需要：

- **MPlib 0.2.1**：需要在 ARM 上自行编译，并打上 RMBench 官方的 screw 规划补丁。FCL 0.7 和 OctoMap 1.10 必须配套使用，混入 OctoMap 1.9 会导致进程退出时 heap corruption。
- **RoboTwin 资产**：从 HuggingFace 下载 `embodiments.zip` 和 `objects.zip`。`demo_clean` 配置用不到 `background_texture.zip`（11 GB），可以不下。

和 GPU 版本相比的差异：

- MPlib 并不是 CuRobo 的逐数值移植。CuRobo 针对 aloha-agilex 的 `frame_bias` 和校准旋转没有加上，规划出的轨迹会有差别。
- 渲染结果没有和 GPU 版本做过逐像素对比。

用 LingBot-VA 在 NPU 上推理，`click_bell` 和 `beat_block_hammer` 两个任务各跑了 1 个 episode，都成功完成。耗时见 [performance.md](performance.md)。

## 建议的步骤

1. 先用本工具的 `check` 和 `render` 确认底层环境可用。
2. 把 benchmark 固定在某个 commit 上，在单独的 checkout 里修改。
3. 修改上面表格中的几处；RoboTwin 2.0 可以直接使用上面的补丁。
4. 对真实任务跑一遍 setup → reset → step，并确认进程能正常退出。

RMBench 的 CPU 移植基于 commit `7d1cdfc7661c273a7a5c5f6126e2d1a7f0a3f4b7`，改法与 RoboTwin 补丁类似，但这份补丁没有收进本仓库。
