<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# SOURCES

Every web page, document and third-party file consulted while building
openftgs-synth, and what was taken from it. Clean-room rules: no FreeTimeGS
implementation, no EasyVolcap, no FreeTimeGS project-page links, no web search for
FreeTimeGS, and no Neural3DV / ENeRF-Outdoor / SelfCap data, rigs or calibrations.
The file formats were implemented from the written task specification only.

| Date | Source | What was taken |
| --- | --- | --- |
| 2026-10-13 | https://www.blender.org/download/lts/ | Current LTS series: 5.2 (latest 5.2.2), 4.5 still maintained. |
| 2026-10-13 | https://download.blender.org/release/ and https://download.blender.org/release/Blender5.2/ | Tarball name `blender-5.2.2-linux-x64.tar.xz`. |
| 2026-10-13 | https://download.blender.org/release/Blender5.2/blender-5.2.2.sha256 | SHA-256 `84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168` of the tarball; the downloaded file matched. |
| 2026-10-13 | https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz | Blender 5.2.2 LTS itself (the program, installed under ~/opt, not redistributed). |
| 2026-10-13 | PyPI: numpy 2.5.4, opencv-python-headless 5.0.0.93, PyYAML 6.0.3 | Post-processing dependencies (installed in .venv). |
| 2026-10-13 | https://polyhaven.com/license | All Poly Haven assets (HDRIs, textures, models) are CC0; no attribution required; redistribution allowed. |
| 2026-10-13 | https://github.com/Poly-Haven/Public-API, .../blob/master/ToS.md, https://api.polyhaven.com/, https://api.polyhaven.com/api-docs/swagger.json | API endpoints (/assets, /info, /files) and terms: free for any use; requests must carry an identifying User-Agent; the credit clause applies to apps showing live API content, not to downloaded CC0 assets. Used only to find direct file URLs. |
| 2026-10-13 | https://ambientcg.com/license -> https://docs.ambientcg.com/license/ | ambientCG assets are CC0 1.0. |
| 2026-10-13 | https://www.kenney.nl/support | Kenney assets are CC0. |
| 2026-10-13 | Web searches: "poly.pizza Quaternius animated character walk idle"; "poly.pizza Quaternius "Animated" man woman character" | Candidate CC0 characters. |
| 2026-10-13 | https://quaternius.com/, https://quaternius.com/faq.html, https://quaternius.com/packs/ultimatedanimatedcharacter.html, https://quaternius.com/packs/animatedman.html, https://quaternius.com/packs/universalanimationlibrary.html, https://quaternius.com/packs/rpgcharacters.html | Quaternius license: "All models are under the CC0 License." Pack downloads are interactive (itch.io / Patreon), so they were not used. |
| 2026-10-13 | https://poly.pizza/u/Quaternius, https://poly.pizza/search/animated%20character, https://poly.pizza/m/cwYvO5UauX, https://poly.pizza/m/9kF7eTDbhO, https://poly.pizza/m/DgOCW9ZCRJ | Rejected candidates: one page lists CC-BY 3.0, one is marked not animated, and one was kept only as a backup. |
| 2026-10-13 | https://poly.pizza/m/c3Ibh9I3udk, https://opengameart.org/content/animated-human-low-poly | Chosen: "Animated Human" by Quaternius, "Public Domain (CC0)" on the asset page. Clip names (Walk, Run, Idle, ...) were read from the GLB itself. |
| 2026-10-13 | https://static.poly.pizza/1a8a9d55-9aa9-43c4-a031-d926e251d80a.glb (HEAD request only) | Backup candidate's availability; not downloaded. |
| 2026-10-13 | https://static.poly.pizza/170235d2-cdeb-4cb2-a82f-4828585138fe.glb | The character file (CC0). |
| 2026-10-13 | https://polyhaven.com/a/<id> for the 27 Poly Haven assets in assets.yaml | Each page shows the CC0 license badge and the author credits recorded in ASSETS.md. |
| 2026-10-13 | https://api.polyhaven.com/assets, /info/<id>, /files/<id> | Asset ids, authors and direct dl.polyhaven.org file URLs + MD5s (recorded in assets.yaml). |
| 2026-10-13 | dl.polyhaven.org files listed in assets.yaml | The CC0 HDRIs, textures and models themselves (SHA-256 in assets.yaml / ASSETS.md). |
| 2026-10-13 | https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt | CC0 1.0 legal code, copied verbatim to dataset/LICENSE (SHA-256 a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499). |

## Facts measured here rather than taken from documentation

- Blender 5.2.2 camera model (tools/probe_blender_camera.py): f_px = lens/36*W with a horizontal sensor fit; cx = W/2 - shift_x*W, cy = H/2 + shift_y*W (continuous pixels); Cycles samples pixel (i, j) around (i+0.5, j+0.5).
- `cycles.use_pixel_jitter` defaults to False in 5.2; setting it to True displaced rendered markers by up to ~1 px, so it is left False.
- Keyframes inserted from Python ignore the keyframe-interpolation user preference in 5.2; interpolation is set on each key explicitly.
- Camera Data "View Z Depth" is planar camera-space z (checked against an analytic tilted plane to 7e-6 m).
- The opencv-python-headless 5.0 wheel is built without OpenEXR; 4.14 is used.
