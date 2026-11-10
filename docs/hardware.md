# 已验证的硬件

这里只记录实际测试过的配置。Apple Silicon、Ampere Altra、AWS Graviton 等其他 ARM 平台尚未测试。

## 鲲鹏 920

| 项目 | 版本 |
|---|---|
| CPU | HiSilicon Kunpeng 920 5250，4 路 × 48 核，aarch64，无 SVE |
| 系统 | openEuler 24.03 LTS-SP3，内核 5.10，glibc 2.38 |
| Python | 3.12，NumPy 1.26.4 |
| SAPIEN | 3.0.2 源码编译的 CPU 版，CPU PhysX |
| Mesa Lavapipe | 26.2.6，LLVM 23.1.4 |
| OIDN | 2.3.3 源码编译，ISPC 1.24.0，`--cpu=cortex-a57` |

本工具的 `render` 验证参数为 320×240、32 spp、光路深度 8、4 线程，各帧耗时依次为 36.3 秒、2.5 秒、2.6 秒，OIDN 降噪耗时 0.4 秒。

### 尝试过的组合

| 组合 | 结果 |
|---|---|
| Mesa 24.0.3 / LLVM 17 | 光栅化可用，不支持光追（`rayTrace: 0`） |
| Mesa 26.2.6，默认 128 位向量宽度 | 构建 BLAS 时崩溃 |
| Mesa 26.2.6，`LP_NATIVE_VECTOR_WIDTH=256` | 通过 |
| SAPIEN 内置的 OIDN 开关 | 在 CPU 构建中不会真正执行降噪 |
| 官方预编译 OIDN 2.4.1 / 2.5.1 | SIGILL（使用了 SVE 指令） |
| OIDN 2.3.3 源码编译，`--cpu=cortex-a57` | 通过 |

### RMBench 上的结果

下面两组结果来自 RMBench 的 CPU 移植工作，不是本工具直接跑出来的。

- **光追**：Press Button 任务，seed 2，使用原始机器人 mesh 和阴影，320×240、32 spp、深度 8、16 线程。第一帧约 32 秒，之后每帧约 8 秒，OIDN 降噪每帧约 0.2 秒。
- **光栅化**：10 个 RMBench 任务在 seed 2 下的 expert 检查全部通过。

这两组结果互相独立：10 个任务只验证了光栅化，光追只验证了 Press Button 一个任务。RoboTwin 与 RMBench 使用相同的底层技术栈，但没有单独做过完整验证。

## 添加新的硬件记录

在新机器上跑通后，欢迎补充一节。请写明 CPU 型号、操作系统、各依赖的版本、`render` 使用的参数和耗时，并附上 `result.json`。只跑过本工具的测试场景，并不代表整个 benchmark 都能在这台机器上运行。
