"""XML plugin for wellformed.

Requires lxml. Install with::

    pip install wellformed[xml]
"""

from __future__ import annotations

try:
    import lxml  # noqa: F401
except ImportError as e:
    raise ImportError("wellformed.xml requires lxml. Install with: pip install wellformed[xml]") from e

from .document import XMLValidatedDocument
from .exceptions import XMLParseError
from .validators import (
    make_relax_ng_validator,
    make_schema_validator,
    make_xml_schema_validator,
    make_xml_wellformed_validator,
)

__all__ = [
    "XMLValidatedDocument",
    "XMLParseError",
    "make_relax_ng_validator",
    "make_schema_validator",
    "make_xml_schema_validator",
    "make_xml_wellformed_validator",
]
