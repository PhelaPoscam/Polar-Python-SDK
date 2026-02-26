from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from awe_polar import app_streamlit  # noqa: E402


if app_streamlit.check_password():
	app_streamlit.main_app()
