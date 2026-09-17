"""Allow `python -m orchestra` to run the kernel CLI."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
