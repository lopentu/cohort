"""Launch the container UI using the same server as a native installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cohort.ui.container import main

if __name__ == '__main__':
    main()
