"""Password hashing for the shared ``users`` table.

The FastAPI app verifies credentials with ``argon2`` (argon2-cffi)
``PasswordHasher().verify(stored_hash, password)`` — which requires the RAW
encoded argon2id hash (``$argon2id$v=19$...``).

Django's own ``make_password`` prefixes the hash with ``argon2$`` (Django
convention), which argon2-cffi rejects with ``InvalidHashError``. So for the
shared ``TWCUser`` records we hash directly with argon2-cffi — the exact
library and call the FastAPI app uses — producing a hash the app can verify
without any transformation. (The panel never *verifies* TWCUser passwords;
only the app does, at login.)
"""
from argon2 import PasswordHasher

_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    """Return a raw argon2id hash verifiable by the FastAPI app."""
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a credential against a stored raw argon2id hash (best-effort)."""
    try:
        return _HASHER.verify(password_hash, password)
    except Exception:  # noqa: BLE001
        return False
