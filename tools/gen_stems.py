"""Dev shim — (re)synthesize the repo's stem pack via the packaged generator.

The synthesizer itself now lives in the package
(`hearcode/adapters/mixer/stem_pack.py`) so a fresh `pip install` can build its
own pack on first run. Contributors can still regenerate the in-repo assets with:

    python tools/gen_stems.py
"""

from __future__ import annotations

from pathlib import Path

from hearcode.adapters.mixer.stem_pack import THEMES, generate

OUT = Path(__file__).resolve().parent.parent / "assets" / "loops"


if __name__ == "__main__":
    print(f"generating stems ({', '.join(THEMES)}) into {OUT} …")
    generate(OUT)
    print("done.")
