"""Generate this bundle report using the common sensitivity renderer."""
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import runpy
import sys

if __name__ == "__main__":
    runpy.run_module("pilot.common.write_sensitivity", run_name="__main__")
