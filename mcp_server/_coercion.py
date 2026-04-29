"""Defensive coercion helpers for MCP tool list-typed parameters (WP-150).

Some MCP bridges double-encode array-valued tool arguments as JSON strings
before they reach the FastMCP/Pydantic validation layer. Pydantic v2 (by
design, unlike v1) refuses to coerce an arbitrary string into a list, so the
call fails with `Input should be a valid list [type=list_type, ...]`.

`_coerce_str_list` is a `BeforeValidator` that:
  * passes `None` through unchanged
  * passes real lists through unchanged
  * parses a JSON-array string (e.g. `'["a","b"]'`) into a list
  * wraps a bare non-JSON string (e.g. `"hello"`) as a single-element list
  * returns malformed-JSON or non-array strings unchanged so Pydantic's strict
    list validator emits its canonical error rather than silently swallowing
    a genuine client bug

A WARNING is logged whenever coercion fires (i.e. on any branch other than
`None` or list passthrough). Real-list callers see no logging side effects.

`StrList` is the only alias used by `mcp_server/server.py` in WP-150.
`make_list_coercer(item_type)` is a future-proofing factory exposed for
non-`str` lists; not used in production today, exercised by U-13.

This module is deliberately private (`_coercion.py`) — it is an internal
helper for the MCP tool surface, not part of any public API.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Callable

from pydantic import BeforeValidator


_LOG = logging.getLogger(__name__)
_MAX_LOGGED_VALUE_CHARS = 200


def _truncate(value: Any) -> str:
    s = repr(value)
    if len(s) > _MAX_LOGGED_VALUE_CHARS:
        return s[:_MAX_LOGGED_VALUE_CHARS] + "...(truncated)"
    return s


def _coerce_str_list(value: Any) -> Any:
    """Coerce a possibly-stringified list parameter into a real list.

    See module docstring for the full contract.
    """
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            # Looks like a JSON array — parse, or surface the type error.
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                # Malformed JSON: leave unchanged so Pydantic reports the
                # real type mismatch rather than us silently wrapping it.
                return value
            if isinstance(parsed, list):
                _LOG.warning(
                    "Coerced JSON-string list parameter to list: %s",
                    _truncate(value),
                )
                return parsed
            return value
        if stripped.startswith("{"):
            # JSON object string is not a list — leave unchanged.
            return value
        # Bare string (e.g. "strand-inbox"): wrap as single-element list.
        _LOG.warning(
            "Coerced bare-string list parameter to single-element list: %s",
            _truncate(value),
        )
        return [value]
    # Any other type (int, dict, ...): pass through and let Pydantic reject.
    return value


# Public alias — this is what `mcp_server/server.py` imports and applies.
StrList = Annotated[list[str] | None, BeforeValidator(_coerce_str_list)]


def make_list_coercer(item_type: type) -> Callable[[Any], Any]:
    """Return a coercer that mirrors `_coerce_str_list` for an arbitrary item type.

    Future-proofing for parameters typed as `list[int] | None`, etc. Not used
    in production today; exposed to keep the extension path obvious for the
    next reviewer who needs a non-`str` list parameter.

    The returned function does NOT enforce inner-type validity — it only
    delegates to `json.loads` for stringified arrays and lets Pydantic's
    own inner-type validator finish the job.
    """
    def coerce(value: Any) -> Any:
        result = _coerce_str_list(value)
        # `_coerce_str_list` was written for str items; for non-str items the
        # bare-string fallback would be wrong, so undo that branch when the
        # caller asked for non-str items.
        if item_type is not str and isinstance(value, str) and isinstance(result, list) \
                and result == [value]:
            # Bare-string wrap was the wrong shape for this item_type; return
            # the original so Pydantic rejects rather than silently coerces.
            return value
        return result
    return coerce


__all__ = ["StrList", "_coerce_str_list", "make_list_coercer"]
