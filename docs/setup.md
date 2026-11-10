# 环境准备

本文介绍如何在一台新的 ARM 机器上准备 sapien-cpu-probe 需要的原生依赖。`configure` 只负责记录这些依赖的位置，不会安装或编译任何东西。

下面所有步骤都建议安装到独立目录，不要改动系统库，也不要改动 `/usr/share/vulkan/icd.d`。

## 1. SAPIEN CPU 构建

PyPI 上的 `sapien` wheel 不能直接在这里使用，需要从源码编译一个关闭 CUDA 的版本。

已验证的源码版本：

| 仓库 | commit |
|---|---|
| SAPIEN | `0847062fa93c4783cbd7521a07abac28fd5c94e7` |
| sapien-vulkan-2 | `e056d244a0a7b4788645253fe48f0e6f7fbb813c` |

编译前先打上本仓库附带的补丁。它只改了两处：一是不再无条件启用 CMake 的 CUDA 语言，二是让 GPU PhysX 相关代码只在开启 CUDA 时编译。

```bash
cd /path/to/SAPIEN
git apply --check /path/to/sapien-cpu-probe/patches/sapien-3.0.2-cpu-build.patch
git apply /path/to/sapien-cpu-probe/patches/sapien-3.0.2-cpu-build.patch
```

关键编译选项：`SAPIEN_CUDA=OFF`、`SAPIEN_PROFILE=OFF`、`CMAKE_BUILD_TYPE=Release`。

补丁并不包含 SAPIEN 的其他依赖。ARM 版 PhysX 5、Vulkan headers、shader 编译器、Eigen 等仍需自行准备。Python binding 要和 core 使用同一个安装目录，并且 Python ABI 一致。不带 CUDA 的构建里，`simsense` 模块不可用。

已验证的 Python 环境：Python 3.12、NumPy 1.26.4、Pillow。

## 2. Mesa Lavapipe

需要 Mesa 26.x 版本的 Lavapipe。Mesa 24.x 的 Lavapipe 虽然能做光栅化渲染，但不支持光追。

已验证的做法是从 conda-forge 安装到独立环境：

```bash
micromamba create -y -p /path/to/mesa-env -c conda-forge 'mesa-lavapipe=26.2.6'
```

装好后，目录里应当有 `lib/libvulkan_lvp.so`。`configure` 会据此生成一份指向它的 ICD 文件，运行时只在子进程中启用。

> 已验证环境用的是现成的 prefix，上面这条安装命令没有在新机器上重新测过。如果版本不同，请重新跑一遍 `render` 并记录结果。

## 3. OIDN（可选）

用于对光追结果降噪。鲲鹏 920 不支持 SVE，官方预编译的 OIDN 2.4 及以上版本会因为非法指令（SIGILL）崩溃，所以需要从源码编译。

需要准备：

- [OIDN 2.3.3 源码包](https://github.com/RenderKit/oidn/releases/tag/v2.3.3)（要带子模块的完整源码包）
- [ISPC 1.24.0 aarch64](https://github.com/ispc/ispc/releases/tag/v1.24.0)
- TBB、CMake、C++ 编译器

```bash
bash scripts/build_oidn.sh \
  /path/to/oidn-2.3.3 \
  /path/to/oidn-build \
  /path/to/oidn-install \
  /path/to/ispc-v1.24.0-linux.aarch64/bin/ispc \
  /path/to/tbb-prefix
```

脚本只编译 CPU 设备，ISPC 目标指定为 `--cpu=cortex-a57`，以生成只用 NEON 的通用代码，与实际 CPU 型号无关。安装完成后，如果缺少 `libtbb.so.12` 这个软链接，脚本会自动补上。

## 4. 生成配置并验证

```bash
sapien-cpu-probe configure \
  --python /path/to/sim-venv/bin/python \
  --mesa-prefix /path/to/mesa-env \
  --library-dir /path/to/sapien-native/lib64 \
  --oidn-prefix /path/to/oidn-install \
  --output .local/my-machine
```

- `--library-dir` 可以重复传多次，按顺序排在 Mesa 和 OIDN 之后。只传确实需要的目录；不确定时先用 `ldd` 检查 SAPIEN 的原生库依赖了什么。
- `--python` 请传 venv 里的 `bin/python`。工具会原样保留这个路径，不解析软链接，否则会丢掉 venv 里的包。
- 配置里是本机的绝对路径，不要提交到仓库（`.local/` 已在 `.gitignore` 中）。生成的 `profile.json` 结构如下：

```json
{
  "schema_version": 1,
  "python": "/path/to/sim-venv/bin/python",
  "icd": "/path/to/profile/lvp.json",
  "library_dirs": ["/path/to/mesa-env/lib", "/path/to/oidn-install/lib64", "/path/to/sapien-native/lib64"],
  "oidn_library": "/path/to/oidn-install/lib64/libOpenImageDenoise.so",
  "threads": 4,
  "vector_width": 256
}
```

然后先运行 `check`，再运行 `render`。如果 `check` 通过但 `render` 崩溃，以 `render` 的结果为准。
