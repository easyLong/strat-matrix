"""Independent launch only: uvicorn app.main:app. Hosts import content_planning instead."""
from .standalone_config import load_config
from .content_planning.main import create_app

app = create_app(load_config())

# Forward existing direct Python callers to the same implementation, never duplicate algorithms.
from .content_planning.standalone_exports import *
