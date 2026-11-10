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

## 建议的步骤

1. 先用本工具的 `check` 和 `render` 确认底层环境可用。
2. 把 benchmark 固定在某个 commit 上，在单独的 checkout 里修改。
3. 修改上面表格中的几处。
4. 对真实任务跑一遍 setup → reset → step，并确认进程能正常退出。

之前做 RMBench CPU 移植时，基于的 commit 是 `7d1cdfc7661c273a7a5c5f6126e2d1a7f0a3f4b7`。那次移植中对规划器和机器人部分的改动没有包含在本仓库里。
