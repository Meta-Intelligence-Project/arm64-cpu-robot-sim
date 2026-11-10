"""Wrapper around lingbot-va-fair wan_va/wan_va_server.py (unmodified).
Overrides runtime config and bypasses FSDP for single-device inference;
model hyper-params (action_snr_shift, used_action_channel_ids, norm_stat) are untouched."""
import os, sys, time, argparse
REPO = os.environ["LINGBOT_REPO"]
sys.path.insert(0, REPO)
T0 = time.monotonic()
from wan_va.configs import VA_CONFIGS
from wan_va.utils import init_logger, logger
import wan_va.wan_va_server as S

p = argparse.ArgumentParser()
p.add_argument("--ckpt", required=True)
p.add_argument("--port", type=int, default=29210)
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--save_root", required=True)
a = p.parse_args()
if int(os.environ.get("WORLD_SIZE", "1")) != 1:
    raise RuntimeError("This wrapper supports one device only")
init_logger()
cfg = VA_CONFIGS["libero"]
cfg.wan22_pretrained_model_name_or_path = a.ckpt
cfg.host = a.host
logger.info(f"[wrapper] ckpt={a.ckpt} host={a.host} port={a.port} action_snr_shift={cfg.action_snr_shift} "
            f"used_action_channel_ids={cfg.used_action_channel_ids} enable_offload={cfg.get('enable_offload')} "
            f"num_inference_steps={cfg.num_inference_steps} action_num_inference_steps={cfg.action_num_inference_steps}")
# --- runtime monkeypatch (no repo file modified) ---
# lingbot-va-fair always calls init_process_group, so _configure_model wraps the
# transformer with FSDP2 even on 1 card. On torch 2.6 + torch_npu, FSDP2 rejects the
# mixed fp32 (_keep_in_fp32_modules) / bf16 params ("FSDP expects uniform original
# parameter dtype"). Use the repo's own non-distributed branch instead:
# eval + cast to param_dtype (bf16, same compute dtype as FSDP MixedPrecision param_dtype) + move to device.
import torch
def _configure_model_single_card(model, shard_fn, param_dtype, device, eval_mode=True):
    if eval_mode:
        model.eval().requires_grad_(False)
    model.to(param_dtype)
    model.to(device)
    return model
S._configure_model = _configure_model_single_card
ns = argparse.Namespace(config_name="libero", port=a.port, save_root=a.save_root)
S.run(ns)
