"""Creates Supabase clients. Keys come from environment variables, never from GitHub."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import Client, create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")
    # A fresh client per call so one user's login never leaks into another's.
    return create_client(SUPABASE_URL, SUPABASE_KEY)
