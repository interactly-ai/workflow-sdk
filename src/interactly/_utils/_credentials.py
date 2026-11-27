"""Which parts of an LLM config hold a credential, as the workflow service judges it.

The server clears these from what a non-admin reads, and puts back the ones an update leaves blank, but only for a
non-admin: an admin is shown them, so for an admin a blank one means "delete it". A credential header an update leaves
out of its header map is deleted for every role. ``llm_configs.update`` carries them across itself, blank or left
out, so that an update built in code doesn't delete what it never meant to touch.

The client can't read the server's declarations (the config mirror leaves the markers out, and the client must not
need it), so the lists are restated here. ``tests/unit/test_drift_guards.py`` compares them with the server's source.
"""

from __future__ import annotations

import re
from typing import FrozenSet, List, Tuple

__all__ = ["CREDENTIAL_FIELDS", "CREDENTIAL_HEADER_MAPS", "is_credential_header"]

#: Fields whose whole value is a credential: the provider ``api_key``, and Bedrock's AWS key pair.
CREDENTIAL_FIELDS: FrozenSet[str] = frozenset({"api_key", "aws_access_key_id", "aws_secret_access_key"})

#: Header maps whose credential entries (by :func:`is_credential_header`) are credentials: the custom gateway's.
CREDENTIAL_HEADER_MAPS: FrozenSet[str] = frozenset({"default_headers"})


def is_credential_header(name: str) -> bool:
    """Whether a header holds a credential, judged by its name as the server judges it.

    The name is split into words, so ``X-Client-Token``, ``client_token`` and ``clientToken`` are alike, and the
    **last** word decides: ``service_token`` is a credential, ``token_count`` only describes one.
    """
    lowered = str(name).lower()
    if lowered in SENSITIVE_HEADER_NAMES or lowered in SENSITIVE_BODY_KEYS:
        return True
    words = _words(name)
    if not words:
        return False
    if words[-1] in SENSITIVE_LAST_WORDS:
        return True
    return len(words) >= 2 and (words[-2], words[-1]) in SENSITIVE_LAST_PAIRS


#: Names the server has always treated as secret.
SENSITIVE_HEADER_NAMES: FrozenSet[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "apikey",
        "x-auth-token",
        "auth-token",
        "x-amz-security-token",
        "x-access-token",
        "access-token",
        "x-secret",
    }
)
SENSITIVE_BODY_KEYS: FrozenSet[str] = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "client_secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
    }
)
#: A name whose last word is one of these names a credential.
SENSITIVE_LAST_WORDS: FrozenSet[str] = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "credential",
        "credentials",
        "assertion",
        "cookie",
        "auth",
        "authentication",
        "authorization",
        "apikey",
    }
)
#: "key" alone is too common (sort_key, cache_key) to count; these pairs are the credential kinds of it.
SENSITIVE_LAST_PAIRS: FrozenSet[Tuple[str, str]] = frozenset(
    {("api", "key"), ("private", "key"), ("access", "key"), ("secret", "key"), ("signing", "key")}
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]+")


def _words(name: str) -> List[str]:
    """``X-Client-Token`` -> ``["x", "client", "token"]``; ``dbPassword`` -> ``["db", "password"]``."""
    spaced = _CAMEL_BOUNDARY.sub(" ", str(name))
    return [word.lower() for word in _NON_ALPHANUMERIC.split(spaced) if word]
