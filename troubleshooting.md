# 已踩过的坑

| 现象 | 原因／定位 | 已验证处理 |
|---|---|---|
| `import sapien` 成功，建场景或拍照 SIGSEGV | 原生驱动可能到 BLAS/JIT 阶段才失败 | 必须运行真实 render；检查 log 与最终 signal |
| Mesa26 软件 RT 在 BLAS 阶段崩溃 | 本机默认 128-bit 向量路径问题 | 在导入 SAPIEN 前设置 `LP_NATIVE_VECTOR_WIDTH=256`；不是宣称 CPU 有 SVE256 |
| 枚举设备但 `rayTrace: 0` | 选到了旧 Mesa24 驱动 | 指定新 Lavapipe ICD；不要用 raster 成功替代 RT 成功 |
| 新 Mesa 仍加载了旧 LLVM | 继承 `LD_PRELOAD` 或错误动态库顺序 | 清除旧 preload；Mesa prefix 的 `lib` 优先；工具仅在子进程内处理 |
| 设了 `oidn`，图像仍噪声很大 | 当前 SAPIEN OIDN bridge 依赖 CUDA interop | 原生 denoiser 设为 none；读取 HDR/Albedo/Normal 后独立 CPU OIDN |
| OIDN SIGILL | 部分预编译二进制用了本机不支持的 SVE 指令 | 使用已验证 OIDN2.3.3 + ISPC1.24.0，显式 `--cpu=cortex-a57` 构建 |
| OIDN 找不到 libtbb.so.12 | dependency installer 复制实文件但遗漏 SONAME symlink | 在自己的安装目录补对应 symlink，或加载匹配 TBB prefix；不覆盖系统库 |
| 机器人能跑，退出时 heap corruption | 本次 MPlib/FCL 与 OctoMap 1.9/1.10 动态库混用 | 使用同一套 FCL0.7 / OctoMap1.10，核对实际链接路径，正常退出也纳入验收 |
| ARM 编译 SAPIEN 仍寻找 nvcc | 项目语言初始化无条件开启 CUDA | 应用附带 CPU build patch，并设置 `SAPIEN_CUDA=OFF` |
| CPU import 被 torch-npu 环境干扰 | 自动设备后端加载 | 用独立 CPU 环境，`TORCH_DEVICE_BACKEND_AUTOLOAD=0` |
| 换了 Python 却丢失 venv 包 | 对 `venv/bin/python` 做 realpath 后执行了底层解释器 | 保留 venv 可执行文件路径；setup 脚本不会解析这个 symlink |

默认 probe 保留三帧，用首次与后续耗时区分 shader/场景初始化开销。图像颜色异常时先检查实际输入／输出与 RGB 通道，不要一开始改材质或颜色空间。

相关上游记录：[Lavapipe 128/256-bit 问题](https://github.com/gfx-rs/wgpu/issues/8637)。上面的结论针对已验收版本；新版本应重新跑探针，不假定旧 workaround 永久必要。
