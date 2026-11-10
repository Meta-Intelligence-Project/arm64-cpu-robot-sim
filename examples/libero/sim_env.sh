# Source only in a dedicated simulation child shell. No global configuration.
: "${SIM_ENV:?Set SIM_ENV to the LIBERO Python environment}"
: "${LIBERO_CONFIG_PATH:?Set LIBERO_CONFIG_PATH to the directory containing config.yaml}"
: "${LINGBOT_REPO:?Set LINGBOT_REPO to the LingBot-VA checkout}"
export MUJOCO_GL=${MUJOCO_GL:-osmesa}
export PYOPENGL_PLATFORM=$MUJOCO_GL
export LD_LIBRARY_PATH=${MESA_PREFIX:-$SIM_ENV}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export __EGL_VENDOR_LIBRARY_DIRS=${MESA_PREFIX:-$SIM_ENV}/share/glvnd/egl_vendor.d
export OMP_NUM_THREADS=${SIM_THREADS:-16} LP_NUM_THREADS=${SIM_THREADS:-16}
export MKL_NUM_THREADS=${SIM_THREADS:-16} OPENBLAS_NUM_THREADS=${SIM_THREADS:-16}
export NUMBA_NUM_THREADS=${SIM_THREADS:-16} TORCH_DEVICE_BACKEND_AUTOLOAD=0
export LIBERO_CONFIG_PATH LINGBOT_REPO
export NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1
