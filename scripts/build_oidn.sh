#!/usr/bin/env bash
# Build already-downloaded OIDN 2.3.3 source. Never install into system directories.
set -euo pipefail
if [[ $# != 5 ]]; then
  echo 'Usage: build_oidn.sh SOURCE BUILD_DIR INSTALL_PREFIX ISPC_BINARY TBB_PREFIX' >&2
  exit 2
fi
src=$(realpath "$1")
build=$(realpath -m "$2")
prefix=$(realpath -m "$3")
ispc=$(realpath "$4")
tbb=$(realpath "$5")
[[ ! -e "$build" && ! -e "$prefix" ]] || { echo 'Use fresh build/install directories' >&2; exit 2; }
cmake -S "$src" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DCMAKE_PREFIX_PATH="$tbb" -DISPC_EXECUTABLE="$ispc" \
  '-DISPC_FLAGS_RELEASE=-O3 --cpu=cortex-a57' \
  -DOIDN_DEVICE_CPU=ON -DOIDN_DEVICE_SYCL=OFF -DOIDN_DEVICE_CUDA=OFF \
  -DOIDN_DEVICE_HIP=OFF -DOIDN_APPS=OFF -DOIDN_FILTER_RTLIGHTMAP=OFF \
  -DOIDN_INSTALL_DEPENDENCIES=ON
cmake --build "$build" --parallel "${BUILD_JOBS:-4}"
cmake --install "$build"
# OIDN's dependency installer may copy the file without the SONAME symlink.
for dir in "$prefix/lib64" "$prefix/lib"; do
  [[ -d "$dir" ]] || continue
  if [[ ! -e "$dir/libtbb.so.12" ]]; then
    files=("$dir"/libtbb.so.12.*)
    if [[ ${#files[@]} == 1 && -f "${files[0]}" ]]; then
      ln -s "$(basename "${files[0]}")" "$dir/libtbb.so.12"
    fi
  fi
done
