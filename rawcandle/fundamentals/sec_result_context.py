"""Additive, bounded SEC recognition; legacy primary matching lives separately."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class _Sections(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.anchor: tuple[str, list[str]] | None = None
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")
        if tag == "td":
            self.parts.append(" ")
        if tag == "a":
            self.anchor = (dict(attrs).get("href") or "", [])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")
        if tag == "a" and self.anchor:
            href, parts = self.anchor
            self.links.append((href, "".join(parts)))
            self.anchor = None

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1].append(data)


def item_202_sections(html: str) -> tuple[str, ...]:
    parser = _Sections()
    parser.feed(html)
    normalized = "".join(parser.parts).replace("\u200b", "").replace("\u00ad", "")
    lines = [" ".join(line.split()) for line in normalized.splitlines() if line.strip()]
    sections = []
    for index, line in enumerate(lines):
        # Only a block beginning with the item heading can open a new path.
        if not re.match(r"^(?:items?\s*)?2\s*\.\s*02(?=$|\W|results?\b)", line, re.I):
            continue
        heading = re.sub(r"[\s\u00ad\u2010-\u2015:;.,-]", "", " ".join(lines[index:index + 3])).lower()
        if not re.match(r"^(?:items?)?202(?:and701)?(?:disclosureof)?results?of(?:financial)?operations?(?:andfinancialcondition)?", heading):
            continue
        end = index + 1
        while end < len(lines) and not re.match(r"^(?:item\s*)?\d\s*\.\s*\d{2}(?!\d)", lines[end], re.I):
            end += 1
        sections.append(" ".join(lines[index:end]))
    return tuple(sections)


def same_accession_document(parent_url: str, document_url: str) -> bool:
    parent = urlsplit(parent_url)
    target = urlsplit(document_url)
    if parent.scheme != "https" or parent.netloc != "www.sec.gov":
        return False
    directory = parent.path.rsplit("/", 1)[0] + "/"
    if not re.fullmatch(r"/Archives/edgar/data/\d+/\d{18}/", directory):
        return False
    return (target.scheme == "https" and target.netloc == parent.netloc
            and not target.query and "%" not in target.path
            and target.path.rsplit("/", 1)[0] + "/" == directory
            and target.path != parent.path
            and target.path.lower().endswith((".htm", ".html", ".txt")))


def linked_result_exhibits(html: str, parent_url: str) -> tuple[str, ...]:
    parser = _Sections()
    parser.feed(html)
    links = []
    for href, label in parser.links:
        target = urlsplit(urljoin(parent_url, href))
        if not same_accession_document(parent_url, target.geturl()):
            continue
        if not re.search(r"(?:99[._ -]?[12]|earnings|press.?release|results)", label + " " + target.path.rsplit("/", 1)[-1], re.I):
            continue
        url = target._replace(fragment="").geturl()
        if url not in links:
            links.append(url)
    # Do not silently choose two from a larger, potentially conflicting set.
    return tuple(links) if len(links) <= 2 else ()


def unsafe_new_event(text: str) -> bool:
    lead = " ".join(text.split())[:1200]
    return bool(re.search(
        r"\b(?:preliminary|partial|pro\s*[- ]?\s*forma|monthly|investor presentation|"
        r"cash receipts|distribution|guidance.only|anticipat\w*|prepare\w* to announce|"
        r"(?:will|expects? to|plans? to)\s+(?:announce|release|report))\b", lead, re.I,
    ))


def result_context(text: str) -> str | None:
    compact = " ".join(text.split())
    if unsafe_new_event(compact):
        return None
    # Require an actual result event, not just a heading or a cover-date match.
    events = re.finditer(
        r"\b(?:announce(?:s|d)?|report(?:s|ed)?|release(?:s|d)?|reporting|announcing)\b.{0,240}?"
        r"\b(?:(?:financial|quarterly|fiscal|operating|annual)\s+)*results\b",
        compact[:6000], re.I,
    )
    for event in events:
        context = compact[max(0, event.start() - 100):event.end() + 650]
        if unsafe_new_event(context):
            continue
        if re.search(r"\b(?:quarter|months|full[- ]year|fiscal year)\b", context, re.I):
            if result_periods(context) or result_fiscal_tokens(context):
                return context
    return None


def result_periods(context: str) -> frozenset[str]:
    return frozenset(re.sub(r"\s+", " ", value).lower() for value in re.findall(
        r"\b(?:quarter|months|year)\b[^.!?]{0,65}?\bended\s+(?:on\s+)?"
        r"([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", context,
    ))


def result_fiscal_tokens(context: str) -> frozenset[str]:
    tokens = set()
    for number, word in enumerate(("first", "second", "third", "fourth"), start=1):
        for year in re.findall(
            rf"\b{word}\s+(?:fiscal\s+)?quarter\s+(?:(?:of\s+)?(?:fiscal\s+year\s+)?)?(\d{{4}})\b",
            context, re.I,
        ):
            tokens.add(f"{year}:Q{number}")
    for number, year in re.findall(r"\bq([1-4])\s+(?:fy\s*)?(\d{4})\b", context, re.I):
        tokens.add(f"{year}:Q{number}")
    return frozenset(tokens)
