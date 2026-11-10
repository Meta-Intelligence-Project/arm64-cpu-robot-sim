# 硬件与环境记录

只记录真正尝试过的配置。当前没有 Apple Silicon、Ampere Altra、Graviton 或其他 ARM CPU 的验收结果。

| 项目 | 已验证环境 |
|---|---|
| CPU | HiSilicon Kunpeng 920；4 sockets × 48 cores；aarch64 |
| 系统 | openEuler 24.03 LTS-SP3；容器所见宿主 Linux 5.10；glibc 2.38 |
| Python / 仿真 | Python 3.12，SAPIEN 3.0.2 自定义 CPU 构建，CPU PhysX |
| 软件 Vulkan | Mesa Lavapipe 26.2.6；设备报告 LLVM 23.1.4 |
| 必要环境 | `LP_NATIVE_VECTOR_WIDTH=256`，指定独立 Lavapipe ICD |
| 去噪 | OIDN 2.3.3 源码构建，ISPC 1.24.0，`--cpu=cortex-a57` |
| 新工具验证 | 见 `examples/kunpeng-validation.json`，有当前探针的完整结果 |

## 原始尝试记录（2026-11-08）

| 尝试 | 结果 |
|---|---|
| Lavapipe 24.0.3 / LLVM17 | raster 可用，报告 `rayTrace: 0`，不能作为光追后端 |
| Lavapipe 26.2.6，默认 128-bit 软件向量宽度 | 方块场景也能在 BLAS 构建时崩溃 |
| 同版本，`LP_NATIVE_VECTOR_WIDTH=256` | 方块与 RMBench Press Button 真实场景光追通过 |
| SAPIEN 原生 OIDN 开关 | 该 CPU 构建没有实际执行 OIDN，不能据此宣称降噪 |
| 预编译 OIDN 2.5.1 / 2.4.1 | 在这台不具备 SVE 的 CPU 上遇到不支持的指令 |
| OIDN 2.3.3 / ISPC 1.24.0，显式 cortex-a57 | 独立 CPU HDR 降噪通过 |

原始 Press Button seed2：原始机器人 mesh、阴影、320×240、32 spp、depth8，16 渲染线程。首次帧约 32.38 秒，后续约 8.22 / 8.11 秒。CPU OIDN 单帧约 0.22–0.25 秒。该耗时只描述这个场景与配置，不是通用性能承诺。

原始 raster CPU 适配记录中 10 个 RMBench 任务在 seed2 的 expert 检查成功；这与上面的单场景光追验收是两组不同记录。不能组合声称 10 个任务都完成了光追策略评估。RobotWin 共用相关底层栈，但没有在本工具里单独验收整套 RobotWin。
