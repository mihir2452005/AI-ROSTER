"""Configuration for the RoastGPT engine.

For MVP, this is just file paths. Swap LIBRARY_PATH for a database/S3 source
later when we move beyond file-based storage.
"""
from pathlib import Path
from os import getenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
LIBRARY_PATH = PROJECT_ROOT / "roast-library"

# Engine behavior
MIN_INTENT_SCORE = 1          # below this, intent is ignored
RECENT_ROAST_WINDOW = 8       # how many recent roasts to penalize for repetition
MAX_SESSION_MESSAGES = 50     # safety cap per session
DEFAULT_PERSONALITY = "sarcastic_friend"

# Input limits — keep these in sync with the API gateway (5MB body cap in
# main.py). Anything longer than MAX_USER_MESSAGE_CHARS is almost certainly
# an abuse attempt (memory pressure, log spam) so reject early.
MAX_USER_MESSAGE_CHARS = 2000
MAX_USERNAME_CHARS = 64
# How many chars of chat history to keep in a single row. Anything beyond
# this is truncated before insertion. Defence-in-depth against log injection
# / XSS payloads in long messages.
MAX_HISTORY_MESSAGE_CHARS = 4000

# Optional override via env
LIBRARY_PATH = Path(getenv("ROAST_LIBRARY_PATH", str(LIBRARY_PATH)))
