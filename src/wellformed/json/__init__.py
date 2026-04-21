"""JSON plugin for wellformed.

Requires jsonschema. Install with::

    pip install wellformed[json]
"""

from __future__ import annotations

try:
    import jsonschema  # noqa: F401
except ImportError as e:
    raise ImportError("wellformed.json requires jsonschema. Install with: pip install wellformed[json]") from e

from .document import JSONValidatedDocument
from .exceptions import JSONParseError
from .validators import (
    make_json_schema_validator,
    make_json_wellformed_validator,
    make_schema_validator,
)

__all__ = [
    "JSONValidatedDocument",
    "JSONParseError",
    "make_json_schema_validator",
    "make_json_wellformed_validator",
    "make_schema_validator",
]
