# RAFT inference source

Source: https://github.com/princeton-vl/RAFT/tree/2888e15a51fa41140771d3f498ed8023cff098d1

This is the exact upstream revision referenced by the RAFT submodule in
`sudip-work` commit `00d414e`. Only the inference modules and BSD-3-Clause
LICENSE are included. Imports are package-relative; PyTorch autocast/meshgrid
calls are updated for the current API. The unused SciPy interpolation helper
is omitted. Training, datasets, CUDA extensions,
demo servers and duplicate environments are not needed by the live bridge.

`ghostdriver/models/raft-small.pth` is the checkpoint from that branch, stored
as an ordinary file so a normal clone has working weights without LFS setup.
SHA-256: `c7d41b9cc88442bb8aa911dbb33086dac55a226394b142937ff22d5578717332`.

`prediction.py` adapts the branch's backward-flow and damped image-warp logic
to actual frame timestamps and the existing authenticated WebRTC stream.
