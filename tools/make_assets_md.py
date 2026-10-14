# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate ASSETS.md from assets.yaml."""
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


def main(out=os.path.join(HERE, "..", "ASSETS.md")):
    assets = yaml.safe_load(open(os.path.join(HERE, "..", "assets.yaml")))
    L = ["<!-- SPDX-License-Identifier: GPL-3.0-or-later -->", "# ASSETS", "",
         "Every third-party asset used to render openftgs-synth. All are CC0-1.0; each license was",
         "checked on the asset's own page on the date shown. Files are fetched with",
         "`tools/fetch_assets.py`, which verifies the SHA-256 values below. Generated from",
         "`assets.yaml` by `tools/make_assets_md.py`.", "",
         "| Asset | Kind | Author(s) | License | Checked | Page |", "| --- | --- | --- | --- | --- | --- |"]
    for a in assets:
        L.append(f"| {a['name']} (`{a['id']}`) | {a['kind']} | {a['author']} | {a['license']} | "
                 f"{a['license_checked']} | {a['page']} |")
    L += ["", "## License evidence", ""]
    for a in assets:
        L.append(f"- `{a['id']}`: {a['license_evidence']}")
    L += ["", "## Downloaded files", "", "| Asset | File | URL | SHA-256 |", "| --- | --- | --- | --- |"]
    for a in assets:
        for f in a["files"]:
            L.append(f"| `{a['id']}` | `{f['path']}` | {f['url']} | `{f['sha256']}` |")
    L += ["", "Not used: SMPL/SMPL-X or any body model, any non-commercial or research-only asset,",
          "Mixamo or other custom-terms character libraries.", ""]
    open(out, "w").write("\n".join(L))


if __name__ == "__main__":
    main(*sys.argv[1:])
