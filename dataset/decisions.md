- **Square pixels everywhere (fx = fy).** The pinhole ground truth is a crop of the
  oversized render, so it shares that render's square pixels. The principal point is
  off-centre in the distorted scenes other than `tiny`/`tiny_unsync`.
- **Depth and masks are point-sampled** at pixel centres (one sample, no filter), not
  antialiased. Masks are binary (0/255).
- **Background images are undistorted** (pinhole geometry), like all ground-truth images.
- **The `tiny` selfcap form is a separate render** (`tiny_unsync`). The n3dv layout needs
  synchronized cameras, so one render cannot serve both.
- **Undistort round-trip rule (owner decision).** cv2.undistort's own bilinear
  resampling costs about 2-3 levels on these textures at 1080p and more at 160x120. A
  scene passes check 2 when the median difference is at most max(1, floor median), the
  mean is at most the floor mean (the floor is a bilinear shift-and-back of the same
  frames), and moving the principal point by half a pixel makes the mean at least 1.2x
  worse.
- **Video colour:** BT.709 matrix, limited range. The transfer is tagged sRGB, which is
  what the frames contain.
- **Character:** "Animated Human" by Quaternius (CC0) ships without textures. It is dressed
  with CC0 Poly Haven fabric textures by rest-pose height bands (trousers, shirt, skin).
- **Cloth** is Blender cloth, baked once per scene with a fixed wind-gust sequence. Sub-frame
  times use Blender's cache interpolation.
- **Denoiser on the GPU (owner decision).** OpenImageDenoise runs on the GPU with fixed
  settings, so repeated renders of a frame can differ by up to 115/65535 in 16 bit (under
  half an 8-bit level). CPU denoising would cap that at 1/65535 but would take about
  158 h instead of about 46 h. The GPU path tracer is not bit-exact on its own either.
- **Depth is float32 (owner decision).**
- **Persistent data** is on within each per-camera Blender process (static BVH reused).
