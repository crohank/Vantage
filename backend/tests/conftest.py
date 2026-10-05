"""Test configuration.

Settings are populated from the environment before any vantage module is
imported, so tests never depend on a developer's .env.
"""

import os

os.environ.setdefault("MONGODB_URI", "mongodb://testhost/vantage_test")
os.environ.setdefault("SEC_EDGAR_USER_AGENT", "Vantage Test tests@vantage.invalid")
os.environ.setdefault("VANTAGE_GIT_SHA", "test")

import pytest

from vantage.config import get_settings


@pytest.fixture
def ten_k_html() -> bytes:
    """A miniature 10-K exercising the three things that break naive parsers.

    1. A table of contents whose rows carry the same text as real headings.
    2. A prose cross-reference that mentions an item without being a heading.
    3. Item 1C, which is outside the canonical map in older filings and must
       still terminate Item 1B rather than being absorbed into it.
    """
    return b"""<html><body>
      <div><table>
        <tr><td><a href="#i1">Item 1. Business</a></td></tr>
        <tr><td><a href="#i1a">Item 1A. Risk Factors</a></td></tr>
        <tr><td><a href="#i1b">Item 1B. Unresolved Staff Comments</a></td></tr>
        <tr><td><a href="#i2">Item 2. Properties</a></td></tr>
      </table></div>

      <div><span>Item&#160;1.&#160;&#160;Business</span></div>
      <div>We design and sell devices. See Part I, Item 1A of this Form 10-K
           under the heading &#8220;Risk Factors&#8221; for more.</div>

      <div><span>Item&#160;1A.&#160;&#160;Risk Factors</span></div>
      <div>Demand may decline.</div>
      <div>Two customers account for 39% of revenue.</div>

      <div><span>Item 1B. Unresolved Staff Comments</span></div>
      <div>None.</div>

      <div><span>Item 1C. Cybersecurity</span></div>
      <div>We run an information security programme.</div>

      <div><span>Item 2 &#8211; Properties</span></div>
      <div>We lease offices.</div>
    </body></html>"""


@pytest.fixture(autouse=True)
def _no_real_mongo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the offline suite off any cluster a local .env happens to name.

    Without this, every call that resolves a store or a checkpointer tries
    the real URI and waits out the connection timeout.
    """
    monkeypatch.setenv("MONGODB_URI", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
