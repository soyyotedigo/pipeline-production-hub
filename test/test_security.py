import sys
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import hash_password, verify_password  # noqa: E402


def test_hash_password_uses_configured_bcrypt_rounds() -> None:
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.bcrypt_rounds = 13
        hashed_password = hash_password("supersecret")

    assert hashed_password.startswith("$2b$13$")
    assert verify_password("supersecret", hashed_password)
