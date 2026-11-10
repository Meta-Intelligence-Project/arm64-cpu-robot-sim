# 环境准备

工具将“配置已有 runtime”和“编译原生依赖”分开。`configure` 只生成一个子进程 profile；它不是一键安装整个 SAPIEN 的脚本。

## 1. 仿真 Python 与 SAPIEN

已验证 Python3.12、NumPy1.26.4、SAPIEN3.0.2 CPU 构建、Pillow。可以复用团队已有的 ARM CPU runtime，保持只读。

新机器必须先取得兼容 ARM 的 SAPIEN CPU 构建；不要假定普通 `pip install sapien` 会得到当前已验证二进制。

本地验证源码基线：

- SAPIEN：`0847062fa93c4783cbd7521a07abac28fd5c94e7`
- sapien-vulkan-2：`e056d244a0a7b4788645253fe48f0e6f7fbb813c`
- 自定义构建对外版本：3.0.2
- 核心编译参数：`SAPIEN_CUDA=OFF`、`SAPIEN_PROFILE=OFF`、Release、CPU PhysX。

`patches/sapien-3.0.2-cpu-build.patch` 是本机源码的两处改动：避免 project 无条件要求 CUDA，以及约束 GPU PhysX 代码编译。它不是完整依赖安装包。使用前在**独立 checkout**执行：

```bash
git apply --check /path/to/sapien-cpu-probe/patches/sapien-3.0.2-cpu-build.patch
git apply /path/to/sapien-cpu-probe/patches/sapien-3.0.2-cpu-build.patch
```

SAPIEN 核心仍需要兼容的 ARM PhysX5、Vulkan headers、shader compiler、Eigen 等依赖。Python binding 使用同一 core 安装目录与 Python ABI；不带 CUDA 的 Python 包不能无条件导入 simsense。附带补丁不替代这些前置条件。当前仓库没有打包／分发本机 native binary。

## 2. Mesa 软件 Vulkan

这次成功环境来自独立 conda-forge prefix，`mesa-lavapipe=26.2.6`，设备报告 LLVM23.1.4。已有 micromamba 时可在**新目录**准备：

```bash
micromamba create -y -p /path/to/new-mesa-env -c conda-forge 'mesa-lavapipe=26.2.6'
```

这是环境重建配方，本工具此次验收复用了现成 prefix，没有重新测试网络下载／包求解。先确认该 channel 仍提供目标架构版本；若换版本，重新运行渲染验收并记录结果。

目录必须包含 `lib/libvulkan_lvp.so`。工具据此生成绝对路径 ICD，并在 child 中设置 `VK_DRIVER_FILES`、`VK_ICD_FILENAMES`、`LP_NATIVE_VECTOR_WIDTH=256`。不要改系统 `/usr/share/vulkan/icd.d`。

## 3. 可选 CPU OIDN

在非 SVE 的鲲鹏920上，使用本次验证的 [OIDN2.3.3 源码发布包](https://github.com/RenderKit/oidn/releases/tag/v2.3.3) 和 [ISPC1.24.0 Linux aarch64](https://github.com/ispc/ispc/releases/tag/v1.24.0)。需要包含子模块的源码发布包、CMake/C++工具链及兼容 TBB prefix。

```bash
bash scripts/build_oidn.sh \
  /path/to/oidn-2.3.3 \
  /path/to/new-oidn-build \
  /path/to/new-oidn-install \
  /path/to/ispc-v1.24.0-linux.aarch64/bin/ispc \
  /path/to/tbb-prefix
```

该脚本使用已验证的 `-DISPC_FLAGS_RELEASE='-O3 --cpu=cortex-a57'`，仅启用 CPU device，并在必要时修复自己安装目录中的 TBB SONAME 链接。不会写系统库。这个 target 是为了生成兼容 NEON 指令，不是说实际 CPU 是 Cortex-A57。

## 4. 配置与验证

使用 README 中的 `configure`。`--library-dir` 可重复传入，按顺序追加到 Mesa/OIDN 后面。不要塞入一堆不确定的系统目录；先检查 native binary 的 `ldd` 输出。

`profiles/example.json` 是结构示例，路径需要换成实际路径。不要提交生成的本机 profile；`.local/` 已忽略。

先 `check_env.py`，再 `render_check.py`。检查通过但 render 崩溃时，以 render 为准。`--denoise` 也必须经过一次实际执行，不仅检查 shared library 是否存在。
