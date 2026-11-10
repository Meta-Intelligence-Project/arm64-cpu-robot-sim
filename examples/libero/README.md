# LIBERO example provenance

`client.py` adapts `evaluation/libero/client.py` from [LingBot-VA](https://github.com/Robbyant/lingbot-va), via the local lingbot-va-fair checkout at `6334d94f8b786a8b95a2343f4b6b237c64a32a36`.
Changes: task/episode CLI, monotonic timing, JSON and frame-array output, imageio video output, and lightweight transport imports. The action execution and history-update protocol are retained. LingBot-VA is Apache-2.0; see `LingBot-VA-LICENSE.txt`.

`server.py` is a single-device runtime adapter for that checkout. It sets the weight path and host, and replaces FSDP wrapping with eval + explicit compute dtype + device transfer. It does not edit the supplied checkout. It is not a general adapter for every upstream revision.

See [the runnable guide](../../docs/libero.md). The simulation uses CPU MuJoCo and software OpenGL rasterization; policy inference requires the separate NPU runtime.
