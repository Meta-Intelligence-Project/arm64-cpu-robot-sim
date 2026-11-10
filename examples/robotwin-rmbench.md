# 接到 RobotWin / RMBench

本库的渲染 probe 不依赖机器人、数据集或 policy server，先把底层链路验证好。

已验证的 SAPIEN3 场景构造方式：

```python
import sapien
sapien.render.set_camera_shader_dir('rt')
sapien.render.set_ray_tracing_samples_per_pixel(32)
sapien.render.set_ray_tracing_path_depth(8)
sapien.render.set_ray_tracing_denoiser('none')
scene = sapien.Scene([
    sapien.physx.PhysxCpuSystem(),
    sapien.render.RenderSystem(device='cpu'),
])
```

运行任务进程时，需要在 **import sapien 之前** 使用 profile 对应的 Vulkan／library 环境。可在自己的启动器里复用下面的库接口；`environment` 只返回字典，不修改当前进程环境：

```python
from pathlib import Path
import subprocess
from sapien_cpu_probe.runtime import load_profile, environment

profile = load_profile('.local/my-machine/profile.json')
output = Path('runs/task-001').resolve()
output.mkdir(parents=True, exist_ok=False)
(output / 'cache').mkdir()
subprocess.run(
    [profile['python'], '/absolute/path/to/your_task_smoke.py'],
    env=environment(profile, output),
    cwd='/absolute/path/to/your/benchmark-checkout',
    check=True,
)
```

注意该环境清除了继承的 `PYTHONPATH`，如任务需要独立 overlay，应由调用者显式添加自己的目录。不要自动导入本机其他项目的 sitecustomize 或模型代码。

RMBench 中原先硬编码 CUDA render device、ray-tracing denoiser 或 CuRobo 的位置需要在独立 checkout 适配：

- 改 CPU PhysX / RenderSystem，并保留原始相机、mesh、材质、灯光与采样设置。
- CPU OIDN 通过 HDR/Albedo/Normal 回读后单独执行；不能仅保留原生 `oidn` 字符串就算完成。
- 调用 CuRobo 的 expert 数据生成还需要 CPU planner。它不是这个小库的功能；若改用 MPlib，须单独记录原来的规划行为与实际变化。
- 纯策略关节控制、expert规划、模型推理是不同环节；“CPU 渲染通过”不说明它们都可直接在 CPU 运行。

本仓库没有提供一条能适配任意 RobotWin/RMBench 版本的 patch 命令。先固定项目 commit，再改对应入口，最后运行真实任务的 setup/step/reset 和退出检查。此前 RMBench 端口的基线为 `7d1cdfc7661c273a7a5c5f6126e2d1a7f0a3f4b7`；其完整 planner/robot 适配没有被打包到本工具。
