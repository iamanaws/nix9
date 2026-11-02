"""Run shared-root deployment with a PXE CPU and a CPU using local boot media."""

import os
from pathlib import Path
import runpy

os.environ["NIX9_PXE_TEST"] = "1"
runpy.run_path(str(Path(__file__).with_name("native_netroot.py")), run_name="__main__")
