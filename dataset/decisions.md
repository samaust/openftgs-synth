- **Square pixels everywhere (fx = fy).** The pinhole ground truth is a crop of the
  oversized render, so it shares that render's square pixels. The principal point is
  off-centre in the distorted scenes other than `tiny`/`tiny_unsync`.
- **Depth and masks are point-sampled** at pixel centres (one sample, no filter), not
  antialiased. Masks are binary (0/255).
- **Background images are undistorted** (pinhole geometry), like all ground-truth images.
- **The `tiny` selfcap form is a separate render** (`tiny_unsync`). The n3dv layout needs
  synchronized cameras, so one render cannot serve both.
- **Undistort round trip on `tiny*`:** at 160x120 cv2.undistort's own bilinear resampling
  costs more than a few 8-bit levels. Check 2 compares those scenes with the bilinear floor
  measured on the same images, and reports the half-pixel-shifted error as a sensitivity
  control.
- **Video colour:** BT.709 matrix, limited range. The transfer is tagged sRGB, which is
  what the frames contain.
- **Character:** "Animated Human" by Quaternius (CC0) ships without textures. It is dressed
  with CC0 Poly Haven fabric textures by rest-pose height bands (trousers, shirt, skin).
- **Cloth** is Blender cloth, baked once per scene with a fixed wind-gust sequence. Sub-frame
  times use Blender's cache interpolation.
