"""WP-154: Tests for hooks/stop.py — close-session scaffold injection.

The Stop hook is part of a layered design with the Mara baseline Stop hook:
the project hook prints a four-question scaffold to stdout (deliberate
memory writes), while the Mara baseline runs silently in the background
(safety-net keyword-driven auto-capture). These tests verify the project
hook's scaffold behaviour and its cooperation lead-in line.
"""
from unittest.mock import patch, MagicMock

import httpx


def test_main_prints_scaffold_when_service_healthy(capsys):
    """Service /health 200 → scaffold printed to stdout."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch("hooks.stop.httpx.get", return_value=mock_response):
        from hooks.stop import main
        main()
    captured = capsys.readouterr()
    assert "Memory close-session reminder" in captured.out
    assert captured.err == ""


def test_main_silent_when_service_unreachable(capsys):
    """Service down (ConnectError) → no stdout, no exception."""
    with patch("hooks.stop.httpx.get", side_effect=httpx.ConnectError("refused")):
        from hooks.stop import main
        main()  # must not raise
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_when_service_times_out(capsys):
    """Service unresponsive (TimeoutException) → silent."""
    with patch("hooks.stop.httpx.get", side_effect=httpx.TimeoutException("timeout")):
        from hooks.stop import main
        main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_when_service_returns_5xx(capsys):
    """Service unhealthy (HTTPStatusError) → silent."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error",
        request=httpx.Request("GET", "http://localhost:8000/health"),
        response=httpx.Response(500),
    )
    with patch("hooks.stop.httpx.get", return_value=mock_response):
        from hooks.stop import main
        main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_on_unexpected_exception(capsys):
    """Unexpected error → caught silently, never disrupts the session."""
    with patch("hooks.stop.httpx.get", side_effect=RuntimeError("boom")):
        from hooks.stop import main
        main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_scaffold_contains_four_question_sections():
    """All four scaffold sections (DECISIONS / INSIGHTS / TODOS / FACTS) present."""
    from hooks.stop import _SCAFFOLD
    for header in ("DECISIONS", "INSIGHTS", "TODOS", "FACTS"):
        assert header in _SCAFFOLD, f"Missing section {header} in scaffold"


def test_scaffold_includes_reinforcement_guidance():
    """Scaffold ends by prompting for selective reinforcement."""
    from hooks.stop import _SCAFFOLD
    assert "reinforce" in _SCAFFOLD.lower()
    assert "selective" in _SCAFFOLD.lower()


def test_scaffold_has_cooperation_lead_in_for_mara_safety_net():
    """Option-3 cooperation: scaffold acknowledges the Mara baseline safety net."""
    from hooks.stop import _SCAFFOLD
    assert "Mara baseline" in _SCAFFOLD
    assert "auto-capture" in _SCAFFOLD
    assert "deliberate" in _SCAFFOLD


def test_scaffold_skip_clause_includes_safety_net_arm():
    """The third skip arm — 'safety-net auto-capture is sufficient' — is present."""
    from hooks.stop import _SCAFFOLD
    text = _SCAFFOLD.lower()
    assert "skip" in text
    assert "safety-net" in text or "safety net" in text


def test_module_docstring_describes_layered_design():
    """The hook module's docstring documents the cooperation contract."""
    import hooks.stop as stop_mod
    doc = stop_mod.__doc__ or ""
    assert "Layered design" in doc or "layered" in doc.lower()
    assert "memory_management_wrapper" in doc
