# AGENTS.md

本文件是 arm64-cpu-robot-sim 的 code agent 操作说明。仓库包含 SAPIEN CPU 光追检查、RoboTwin / RMBench 接入经验和 LIBERO CPU 仿真示例。下面的默认流程使用仓库内的 `arm64-cpu-robot-sim` 工具；LIBERO 任务见文末的独立示例。人类读者请看 [README.md](README.md)。

## 流程

1. 先读 [docs/hardware.md](docs/hardware.md) 和 [docs/troubleshooting.md](docs/troubleshooting.md)。没在 hardware.md 里出现过的硬件，按"未验证"处理。
2. 找到用户已有的仿真 Python 环境、Mesa 目录和 SAPIEN 原生库目录。路径要问用户，或者在本机实际确认，不要照搬其他机器上的路径。
3. 运行 `arm64-cpu-robot-sim configure`（未安装时在仓库根目录用 `python -m arm64_cpu_robot_sim configure`）生成配置，输出到一个新目录。缺依赖时，对照 [docs/setup.md](docs/setup.md) 告诉用户具体缺什么。
4. 先跑 `check`，再跑 `render`，每次用新的输出目录。资源紧张时，可以先用 `--width 160 --height 120 --spp 8`。
5. 看退出码、`result.json` 和 `worker.log`。只有退出码为 0 才算成功；即使图片已经生成，进程崩溃也算失败。
6. 打开输出的 PNG，确认画面里有红色、蓝色、银色三个方块，还有地面和阴影。不要只靠图像方差来判断颜色或材质对不对。
7. 只有用户需要降噪、并且已经准备好 CPU OIDN 时，才加 `--denoise`。汇报结果时说清楚哪张是原始图，哪张是降噪后的。
8. 在新硬件上跑通后，经用户同意，可以在 docs/hardware.md 里补充记录。一次测试场景通过，不能说成整个 benchmark 都验证过了。

## 约束

- 不修改 shell 配置、系统 ICD、系统动态库或别人共用的 Python 环境。所有环境变量只在子进程里设置。
- 不结束正在运行的训练或仿真进程，也不连接 policy server。本工具不需要网络。
- 不退回光栅化，不简化机器人 mesh，也不为了让检查通过去修改判定条件。
- 不能把 `set_ray_tracing_denoiser('oidn')` 当作已经执行了 CPU 降噪的证据。
- OIDN 编译时的 `--cpu=cortex-a57` 和 Lavapipe 的 `LP_NATIVE_VECTOR_WIDTH=256` 是两回事：前者决定生成哪些机器指令，后者是软件驱动生成代码时的配置。

## 开发

```bash
python -m unittest discover -s tests -v
```

单元测试不依赖 SAPIEN。测试通过不代表原生链路正常；改动后要在真实配置上跑一遍 `render`。

## LIBERO 独立示例

用户明确要求 LIBERO 闭环时，按 [docs/libero.md](docs/libero.md) 使用 `examples/libero/`。上文“不连接 policy server”和“不退回光栅化”针对 SAPIEN probe；LIBERO 本来使用 MuJoCo 软件光栅化，并需要连接策略服务。只启动和连接本次获准使用的独立服务，不碰其他作业。先检查 NPU/端口占用，结束后释放自己的服务。

结果必须同时记录客户端退出码、每个 episode 的 success、权重版本和实际模型工作树。客户端 exit 0 不表示任务成功；单个 episode 成功不表示 benchmark 成功率。不得把 LIBERO 软件光栅化写成 CPU 光追。
