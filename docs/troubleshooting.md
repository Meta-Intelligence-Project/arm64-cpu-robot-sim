# 常见问题

以下问题都在鲲鹏 920 上实际遇到过。如果换用更新版本的 Mesa、SAPIEN 或 OIDN，有些问题可能已经不存在，请以 `render` 的实际结果为准。

## 渲染

**`import sapien` 正常，但建场景或拍照时 SIGSEGV**

很多原生驱动的问题，要到构建 BLAS（光追加速结构）或 JIT 编译时才会暴露。只看 `import sapien` 能否成功说明不了问题，需要跑一次 `render`，再看 `worker.log` 和结果里的 `signal` 字段。

**Lavapipe 在构建 BLAS 时崩溃**

Mesa 26 的 Lavapipe 在 ARM 上默认使用 128 位向量宽度，光追会在这里崩溃。设置 `LP_NATIVE_VECTOR_WIDTH=256` 可以绕过，本工具已经自动设置。这个变量只影响 Lavapipe 软件生成代码的方式，并不表示 CPU 支持 256 位 SVE。上游相关讨论见 [gfx-rs/wgpu#8637](https://github.com/gfx-rs/wgpu/issues/8637)。

**设备列表里显示 `rayTrace: 0`**

加载到了旧版 Mesa（24.x）。确认 `--mesa-prefix` 指向 Mesa 26 的环境。不要因为光栅化能出图，就认为光追也可用。

**用的是新 Mesa，却加载了旧 LLVM**

通常是继承了 `LD_PRELOAD`，或者动态库搜索顺序不对。本工具会在子进程里清掉 `LD_PRELOAD`，并把 Mesa 的 `lib` 目录排在最前面。如果在其他启动器里遇到这个问题，可以使用 `sapien_cpu_probe.runtime.environment()` 生成同样的环境。

## 降噪

**调用了 `set_ray_tracing_denoiser('oidn')`，图像还是很多噪点**

SAPIEN 内置的 OIDN 接口依赖 CUDA interop，在 CPU 构建里实际上不会执行降噪。解决办法是把内置 denoiser 设为 `none`，读回 HDR、Albedo、Normal 三个 buffer 后，再单独调用 CPU OIDN。本工具的 `--denoise` 就是这样做的。

**OIDN 报 SIGILL**

官方预编译的 OIDN 2.4.1 和 2.5.1 使用了 SVE 指令，鲲鹏 920 不支持。请按 [setup.md](setup.md#3-oidn可选) 从源码编译 2.3.3。

**找不到 `libtbb.so.12`**

OIDN 的依赖安装步骤复制了 TBB 的实际库文件，但没有创建 SONAME 软链接。`scripts/build_oidn.sh` 会自动补上；手动编译的话，在 OIDN 的安装目录里补一个软链接即可，不要改系统库。

## 编译与环境

**在 ARM 上编译 SAPIEN 时 CMake 要找 nvcc**

SAPIEN 的 CMakeLists 会无条件启用 CUDA 语言。打上 `patches/sapien-3.0.2-cpu-build.patch`，并设置 `SAPIEN_CUDA=OFF`。

**机器人场景能运行，但进程退出时报 heap corruption**

MPlib 依赖的 FCL 和 OctoMap 混用了两个版本（OctoMap 1.9 和 1.10）。统一使用 FCL 0.7 和 OctoMap 1.10，并用 `ldd` 确认实际链接的路径。进程能否正常退出也要作为验收的一部分。

**在装了 torch-npu 的环境里，`import` 被干扰**

PyTorch 会自动加载设备后端。仿真请使用独立的 CPU 环境，并设置 `TORCH_DEVICE_BACKEND_AUTOLOAD=0`，本工具已经自动设置。

**换成 venv 的 Python 后，venv 里的包找不到了**

对 `venv/bin/python` 做了 `realpath`，实际执行的是底层的系统解释器。要直接使用 venv 里的路径，`configure` 不会解析这个软链接。

## 性能

第一帧包含 shader 和 JIT 编译，耗时明显更长。在鲲鹏 920 上，320×240、4 线程时第一帧约 35 秒，之后每帧约 0.7 秒（8 spp）到 2.5 秒（32 spp）。如果 `render` 超时，可以加大 `--timeout`，或者先降低分辨率和 spp。
