"""Bundle entry point; numerical implementation lives in pilot.common.run."""
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

import sys
from pathlib import Path
from pilot.common.run import main

if __name__ == "__main__":
    defaults = ['--models', 'CRE', '--no-year-season', '--cache-prefix', 'no_year_season_', '--warm-start', 'pilot/initial/results.json', '--output', 'pilot/no_year_season/results.json']
    # Explicit user options take priority over bundle defaults.
    j = 0
    while j < len(defaults):
        option = defaults[j]
        width = 1 if option in ('--no-year-season', '--cohort-instead-of-wave') else 2
        if not any(a == option or a.startswith(option+"=") for a in sys.argv[1:]):
            sys.argv.extend(defaults[j:j+width])
        j += width
    main()
