"""Start the local image workbench: python tools/image_workbench.py [--port 8765] [--creative].

Every argument is handed to image_workbench.server.main untouched, including
--creative / --no-creative / --creative-root for the drawing workbench.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from image_workbench.server import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
