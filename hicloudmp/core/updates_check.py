"""Manual update check against the GitHub releases API.

Never called automatically - the settings dialog exposes a button, and
the only popup is a release-offer dialog triggered BY that check (the
app stays popup-free otherwise).
"""
import re

import requests

APP_VERSION = "1.0.5"  # bump together with every release tag
RELEASES_URL = ("https://api.github.com/repos/PhantomPixelDev/"
                "HiCloudMP/releases/latest")
RELEASES_PAGE = "https://github.com/PhantomPixelDev/HiCloudMP/releases"


def latest_release(timeout=(10, 30)):
    """{"tag": 'vX.Y.Z', "url": html_url} or raises on network failure."""
    r = requests.get(RELEASES_URL,
                     headers={"User-Agent": "HiCloudMP"},
                     timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return {"tag": str(data.get("tag_name", "") or ""),
            "url": str(data.get("html_url", "") or RELEASES_PAGE)}


def compare_versions(mine, tag):
    """-1 local older / 0 equal / 1 local newer / None when unreadable."""
    try:
        a = _parts(mine)
        b = _parts(tag)
    except (AttributeError, ValueError):
        return None
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _parts(v):
    v = str(v).strip().lower().lstrip("v")
    if "rc" in v or "beta" in v or "alpha" in v:
        raise ValueError("pre-release tags not compared here")
    nums = re.findall(r"\d+", v)
    if not nums:
        raise ValueError("no numeric parts")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))
