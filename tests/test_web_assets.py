import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _panel_source():
    return (ROOT / "web_panel.html").read_text(encoding="utf-8")


def test_slider_background_helper_defined_before_first_use():
    """setSliderBG must be a single real function definition, declared before
    its first call site — ReferenceError-at-runtime is the regression this pins."""
    src_txt = _panel_source()
    def_idx = src_txt.find("function setSliderBG")
    assert def_idx != -1, "setSliderBG function definition missing"
    first_use = src_txt.find("setSliderBG(")
    assert first_use != -1
    assert def_idx < first_use, "setSliderBG referenced before its definition"
    assert src_txt.count("function setSliderBG") == 1, "exactly one definition"
    assert "typeof setSliderBG" not in src_txt, "stale typeof guard now the helper is real"


def test_slider_background_helper_defined_once():
    """The one true helper (setSliderBG) must exist and wrap the slider painter."""
    src_txt = _panel_source()
    assert re.search(r"function\s+setSliderBG\s*\(", src_txt), "setSliderBG helper missing"
    assert re.search(r"\b(let|var|const)\s+userSeeking\b", src_txt), "userSeeking must be declared"


def test_ping_pill_present_and_wired():
    """Connection indicator: ids exist, polls /api/ping, shows latency."""
    src_txt = _panel_source()
    for needle in ("ping-pill", "ping-dot", "ping-text", "api/ping"):
        assert needle in src_txt, needle
    assert "Offline" in src_txt, "broken connection must read Offline, not blank"
    assert "Connected" in src_txt, "healthy connection shows ms latency"


def test_progress_poll_skips_while_hidden():
    """The 1 Hz get_progress poll must not fetch while the tab is hidden —
    a background tab otherwise keeps the server busy for nothing."""
    src_txt = _panel_source()
    hits = [m.start() for m in re.finditer(re.escape("'get_progress'"),
                                           src_txt)]
    assert hits, "progress poll missing"
    poll_idx = hits[-1]  # the setInterval poll is the last emit site
    near = src_txt[max(0, poll_idx - 700):poll_idx]
    assert re.search(r"document\.hidden", near), (
        "1 Hz poll must check document.hidden before emitting")
