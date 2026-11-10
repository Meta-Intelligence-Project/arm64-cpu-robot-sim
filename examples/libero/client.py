"""Instrumented LIBERO closed-loop client for lingbot-va (NPU server).

The control loop (init: reset -> set_init_state -> 5 zero-action steps; per chunk:
infer -> execute actions, keyframe every action_per_frame steps -> compute_kv_cache
with executed action chunk; stop at done or env timestep >= 800) is copied from
lingbot-va-fair/evaluation/libero/client.py. Differences:
  * timing instrumentation (time.monotonic) for env construction, physics step,
    camera rendering, policy inference;
  * max episodes / task list from CLI; JSON timing + frame arrays;
  * lerobot.write_json replaced by json.dump (lerobot not installed in sim env);
  * frames saved as mp4 with imageio (same as original).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

T_PROCESS_START = time.monotonic()

# Import only the lightweight transport package, not the NPU model package.
sys.path.insert(0, str(Path(os.environ["LINGBOT_REPO"]) / "wan_va/utils/Simple_Remote_Infer"))
from deploy.websocket_client_policy import WebsocketClientPolicy

T_IMPORT0 = time.monotonic()
from libero.libero import benchmark  # noqa: E402
from libero.libero.envs import OffScreenRenderEnv  # noqa: E402
import robosuite.utils.binding_utils as bu  # noqa: E402
import imageio  # noqa: E402
T_IMPORT1 = time.monotonic()

# ---------------------------------------------------------------- render timing
RENDER_TIMES = []  # every MjSim.render call (one per camera per obs)
_orig_render = bu.MjSim.render


def _timed_render(self, *a, **k):
    t0 = time.monotonic()
    out = _orig_render(self, *a, **k)
    RENDER_TIMES.append(time.monotonic() - t0)
    return out


bu.MjSim.render = _timed_render


def _extract_obs(obs):
    agentview = np.ascontiguousarray(obs["agentview_image"][::-1])
    eye_in_hand = np.ascontiguousarray(obs["robot0_eye_in_hand_image"][::-1])
    return {"observation.images.agentview_rgb": agentview,
            "observation.images.eye_in_hand_rgb": eye_in_hand}


class StepTimer:
    def __init__(self):
        self.step_total = []   # env.step wall time (physics + obs incl. render)
        self.step_render = []  # render time inside that env.step
        self.infer = {"reset": [], "action": [], "kv_cache": []}

    def step(self, env, action):
        n0 = len(RENDER_TIMES)
        t0 = time.monotonic()
        obs, rew, done, info = env.step(action)
        dt = time.monotonic() - t0
        self.step_total.append(dt)
        self.step_render.append(sum(RENDER_TIMES[n0:]))
        return obs, done

    def call(self, model, kind, payload):
        t0 = time.monotonic()
        ret = model.infer(payload)
        self.infer[kind].append(time.monotonic() - t0)
        return ret


def stats(x):
    if not x:
        return None
    a = np.asarray(x, dtype=np.float64)
    return {"n": int(a.size), "mean_s": float(a.mean()), "median_s": float(np.median(a)),
            "p90_s": float(np.percentile(a, 90)), "min_s": float(a.min()), "max_s": float(a.max()),
            "sum_s": float(a.sum())}


def run_one(model, bench_name, task_idx, episode_idx, out_dir, res, max_steps):
    rec = {"task_idx": task_idx, "episode_idx": episode_idx}
    t_ep0 = time.monotonic()
    bd = benchmark.get_benchmark_dict()
    bi = bd[bench_name]()
    prompt = bi.get_task(task_idx).language
    rec["prompt"] = prompt
    env_args = {"bddl_file_name": bi.get_task_bddl_file_path(task_idx),
                "camera_heights": res, "camera_widths": res}
    init_states = bi.get_task_init_states(task_idx)

    t0 = time.monotonic()
    env = OffScreenRenderEnv(**env_args)
    rec["env_construct_s"] = time.monotonic() - t0

    T = StepTimer()
    t0 = time.monotonic()
    env.reset()
    env.set_init_state(init_states[episode_idx % init_states.shape[0]])
    for _ in range(5):
        obs, _ = T.step(env, [0.] * 7)
    rec["env_reset_and_init_s"] = time.monotonic() - t0
    n_init_steps = len(T.step_total)
    first_obs = _extract_obs(obs)
    first_frame = first_obs["observation.images.agentview_rgb"].copy()
    rec["env_cold_start_s"] = rec["env_construct_s"] + rec["env_reset_and_init_s"]

    T.call(model, "reset", dict(reset=True, prompt=prompt))

    full_obs_list = [first_obs]
    done = False
    first = True
    n_chunks = 0
    while env.env.timestep < max_steps:
        ret = T.call(model, "action", dict(obs=first_obs, prompt=prompt))
        action = ret["action"]
        n_chunks += 1
        key_frame_list = []
        assert action.shape[2] % 4 == 0
        action_per_frame = action.shape[2] // 4
        start_idx = 1 if first else 0
        for i in range(start_idx, action.shape[1]):
            for j in range(action.shape[2]):
                obs, done = T.step(env, action[:, i, j])
                ob = _extract_obs(obs)
                if done:
                    break
                if (j + 1) % action_per_frame == 0:
                    full_obs_list.append(ob)
                    key_frame_list.append(ob)
            if done:
                break
        first = False
        if done:
            break
        T.call(model, "kv_cache", dict(obs=key_frame_list, compute_kv_cache=True, imagine=False, state=action))
        print(f"[task {task_idx} ep {episode_idx}] chunk {n_chunks} env_t={env.env.timestep} "
              f"last_infer={T.infer['action'][-1]:.2f}s", flush=True)

    last_frame = np.ascontiguousarray(obs["agentview_image"][::-1]).copy()
    rec["success"] = bool(done)
    rec["env_timestep_final"] = int(env.env.timestep)
    rec["policy_steps"] = len(T.step_total) - n_init_steps
    rec["init_zero_steps"] = n_init_steps
    rec["action_chunks"] = n_chunks
    rec["action_chunk_shape"] = list(action.shape)

    t0 = time.monotonic()
    env.close()
    rec["env_close_s"] = time.monotonic() - t0
    rec["episode_total_s"] = time.monotonic() - t_ep0

    physics = [a - b for a, b in zip(T.step_total, T.step_render)]
    rec["timing"] = {
        "env_step_total_incl_render": stats(T.step_total),
        "env_step_physics_and_obs_excl_render": stats(physics),
        "render_per_step_all_cameras": stats(T.step_render),
        "policy_infer_action_npu_roundtrip": stats(T.infer["action"]),
        "policy_kv_cache_update_roundtrip": stats(T.infer["kv_cache"]),
        "policy_reset_roundtrip": stats(T.infer["reset"]),
    }
    sum_sim = float(np.sum(T.step_total))
    sum_pol = float(np.sum(T.infer["action"]) + np.sum(T.infer["kv_cache"]) + np.sum(T.infer["reset"]))
    rec["breakdown_s"] = {"sim_steps_total": sum_sim, "policy_total": sum_pol,
                          "other": rec["episode_total_s"] - sum_sim - sum_pol}

    ep_dir = Path(out_dir) / bench_name / f"{task_idx}_{prompt.replace(' ', '_')}"
    ep_dir.mkdir(parents=True, exist_ok=True)
    vid = ep_dir / f"{episode_idx}_{done}.mp4"
    frames = [np.hstack([o["observation.images.agentview_rgb"], o["observation.images.eye_in_hand_rgb"]])
              for o in full_obs_list]
    imageio.mimsave(str(vid), frames, fps=15)
    rec["video"] = str(vid)
    np.save(ep_dir / f"{episode_idx}_first_last_agentview.npy", np.stack([first_frame, last_frame]))
    rec["first_last_npy"] = str(ep_dir / f"{episode_idx}_first_last_agentview.npy")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="libero_10")
    ap.add_argument("--tasks", type=int, nargs="+", default=[0])
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--port", type=int, default=29210)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--res", type=int, default=128)
    ap.add_argument("--max-steps", type=int, default=800)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    model = WebsocketClientPolicy(host=a.host, port=a.port)
    t_connect = time.monotonic() - t0
    episodes = []
    for task in a.tasks:
        for ep in range(a.episodes):
            r = run_one(model, a.benchmark, task, ep, a.out_dir, a.res, a.max_steps)
            print(json.dumps({k: v for k, v in r.items() if k != "timing"}), flush=True)
            episodes.append(r)
            with open(Path(a.out_dir) / "episodes_partial.json", "w") as f:
                json.dump(episodes, f, indent=1)

    meta = {
        "process_total_s": time.monotonic() - T_PROCESS_START,
        "import_libero_robosuite_s": T_IMPORT1 - T_IMPORT0,
        "ws_connect_s": t_connect,
        "MUJOCO_GL": os.environ.get("MUJOCO_GL"),
        "PYOPENGL_PLATFORM": os.environ.get("PYOPENGL_PLATFORM"),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
        "cpu_affinity_count": len(os.sched_getaffinity(0)),
        "resolution": [a.res, a.res], "cameras": ["agentview", "robot0_eye_in_hand"],
        "benchmark": a.benchmark, "tasks": a.tasks, "episodes_per_task": a.episodes,
        "max_steps": a.max_steps,
    }
    with open(Path(a.out_dir) / "client_run.json", "w") as f:
        json.dump({"meta": meta, "episodes": episodes}, f, indent=1)
    print("CLIENT_DONE", json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
