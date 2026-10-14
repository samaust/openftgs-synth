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
