"""Organized experiment packages and compatibility for private legacy pickles."""
import sys
import os
# Historical entry scripts set these before importing NumPy. Preserve that
# order when loading class aliases; PILOT_BLAS_THREADS still controls fits.
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
from .common import panel_core, regime_core, plain_core, specification_core

# Historical cached objects refer to these pre-migration class modules.
# Keep aliases without leaving duplicate source files at the pilot root.
for _module in (panel_core, regime_core, plain_core, specification_core):
    sys.modules.setdefault(_module.__name__.rsplit('.', 1)[-1], _module)
