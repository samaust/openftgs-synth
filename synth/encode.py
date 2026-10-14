# SPDX-License-Identifier: GPL-3.0-or-later
"""Video encoding with the system ffmpeg, and ffprobe checks."""
import json

import numpy as np
import os
import subprocess

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def encode(frames_dir, fps, out, lossless):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp.mp4"
    cmd = [FFMPEG, "-nostdin", "-y", "-loglevel", "error", "-framerate", str(fps),
           "-i", os.path.join(frames_dir, "%06d.png")]
    if lossless:
        cmd += ["-c:v", "libx264rgb", "-qp", "0", "-preset", "medium", "-pix_fmt", "rgb24"]
    else:
        cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "iec61966-2-1",
                "-color_range", "tv"]
    cmd += ["-r", str(fps), "-movflags", "+faststart", "-map_metadata", "-1", "-fflags", "+bitexact", tmp]
    subprocess.run(cmd, check=True)
    os.replace(tmp, out)


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,pix_fmt,width,height,nb_read_frames,r_frame_rate",
                        "-of", "json", path], check=True, capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    s["nb_read_frames"] = int(s["nb_read_frames"])
    return s


def decode_rgb(path, W, H):
    """Decode a video to a uint8 array [N, H, W, 3] (RGB) with ffmpeg."""
    import numpy as np
    r = subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-i", path, "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], check=True, capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W, 3)


def iter_frames(path, W, H):
    """Yield decoded RGB uint8 frames one at a time."""
    import numpy as np
    p = subprocess.Popen([FFMPEG, "-nostdin", "-loglevel", "error", "-i", path, "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = W * H * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.stdout.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg decode failed: {path}")


def check_lossless(video, frames_dir, W, H):
    """Lossless video must decode bit-exactly to the source PNG frames."""
    import cv2
    files = sorted(os.listdir(frames_dir))
    k = 0
    for k, fr in enumerate(iter_frames(video, W, H)):
        ref = cv2.imread(os.path.join(frames_dir, files[k]))[..., ::-1]
        if not np.array_equal(fr, ref):
            raise RuntimeError(f"lossless mismatch at frame {k}: {video}")
    if k + 1 != len(files):
        raise RuntimeError(f"lossless frame count mismatch: {video}")
