"""Text extraction tests: the evidence index is only as good as this text."""

from __future__ import annotations

from scholarmind.ingestion.fetcher import _normalise_text
from scholarmind.ingestion.text import MIN_REGION_CHARS, html_to_text

NAV_FILLER = "Apply Now News Events Contact Us About Us Search Login Menu " * 6


def _page(body: str, *, main: bool = True) -> str:
    wrapper = "main" if main else "div"
    return f"""<!doctype html>
<html><head><title>Chevening</title><style>.x{{color:red}}</style></head>
<body>
<nav>{NAV_FILLER}</nav>
<header>Skip to content</header>
<{wrapper}>
  <h1>Eligibility</h1>
  <p>{body}</p>
</{wrapper}>
<footer>Copyright 2026. All rights reserved. {NAV_FILLER}</footer>
<script>var tracking = "do not index me";</script>
</body></html>"""


def test_main_region_wins_over_navigation() -> None:
    body = (
        "To be eligible for a Chevening Scholarship you must have completed all "
        "components of your undergraduate degree and have at least two years of "
        "work experience, which may include voluntary work and internships."
    )
    text = html_to_text(_page(body))

    assert body[:60] in text
    assert "Copyright 2026" not in text
    assert "Skip to content" not in text
    assert "do not index me" not in text
    assert "Apply Now News Events" not in text
    assert "color:red" not in text


def test_body_is_used_when_there_is_no_main_region() -> None:
    body = (
        "Applicants must submit a transcript, a passport copy and a letter of "
        "recommendation before the closing date of the programme."
    )
    text = html_to_text(_page(body, main=False))

    assert "Applicants must submit a transcript" in text
    assert "Copyright 2026" not in text


def test_short_main_falls_back_to_the_full_body() -> None:
    # A card with a link is not the page's content; the body is.
    html = (
        "<html><body><main><a href='/x'>Apply</a></main>"
        "<div>" + ("The deadline for applications is 13 October 2026. " * 20) + "</div>"
        "</body></html>"
    )
    text = html_to_text(html)

    assert "deadline for applications is 13 October 2026" in text


def test_paragraph_breaks_survive() -> None:
    html = "<html><body><main><p>First paragraph.</p><p>Second paragraph.</p></main></body></html>"
    text = html_to_text(html)

    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "First paragraph.Second paragraph." not in text


def test_entities_are_decoded() -> None:
    html = "<html><body><main><p>Fees &amp; funding &ndash; 2026</p></main></body></html>"
    assert "Fees & funding" in html_to_text(html)


def test_table_row_stays_on_one_line() -> None:
    html = (
        "<html><body><main><table>"
        "<tr><th>Application deadline</th><td>13 October 2026</td></tr>"
        "<tr><th>Course level</th><td>Postgraduate</td></tr>"
        "</table></main></body></html>"
    )
    text = html_to_text(html)
    lines = [line for line in text.splitlines() if "deadline" in line.lower()]

    assert lines, text
    assert "13 October 2026" in lines[0]


def test_definition_list_keeps_term_and_value_together() -> None:
    html = "<html><body><main><dl><dt>Stipend</dt><dd>1,347 GBP per month</dd></dl></main></body></html>"
    line = html_to_text(html).splitlines()[0]

    assert "Stipend" in line and "1,347 GBP per month" in line



def test_empty_document_returns_empty_text() -> None:
    assert html_to_text("") == ""
    assert html_to_text("<html><body></body></html>") == ""


def test_normalise_text_dispatches_html_and_plain_text() -> None:
    html = _page("Applications close on 13 October 2026 and open on 5 August.")
    assert "13 October 2026" in _normalise_text(html.encode("utf-8"))
    # Plain text passes through untouched (a JSON or text/plain response).
    assert _normalise_text(b'{"a": 1}') == '{"a": 1}'


def test_min_region_threshold_is_a_sane_size() -> None:
    assert 100 <= MIN_REGION_CHARS <= 1000
