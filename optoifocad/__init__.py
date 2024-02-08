"""Optocad to Ifocad input script converter"""

PROGRAM = __name__
AUTHORS = ["Sean Leavey"]
PROJECT_URL = "https://github.com/SeanDS/optoifocad"

# Get package version.
try:
    from ._version import version as __version__
except ImportError:
    raise FileNotFoundError("Could not find version.py. Ensure you have run setup.")
