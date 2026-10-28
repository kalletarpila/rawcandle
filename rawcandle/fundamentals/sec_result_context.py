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


def _pending_result_trigger(prefix: str, verb: str) -> bool:
    """Reject a pending verb, not an actual report with outlook elsewhere.

    The caller supplies at most 100 characters immediately before the trigger.
    Only its governing clause/auxiliary is inspected; later dates and result
    words cannot turn a scheduled or conditional announcement into an event.
    """
    clause = re.split(r"[.!?;]", prefix)[-1]
    pending = (
        r"\b(?:will|shall|would|may|might|could|should)\s+"
        r"(?:(?:not|be|have|been|being|soon|later|\w+ly)\s+)*$",
        r"\b(?:is|are|was|were)\s+(?:expected|scheduled|planned|anticipated|due)"
        r"\s+to\s+(?:(?:not|be)\s+)*$",
        r"\b(?:expects?|expected|expecting|plans?|planned|planning|"
        r"intends?|intended|intending|prepares?|prepared|preparing)"
        r"\s+to\s+(?:be\s+)?$",
    )
    if any(re.search(pattern, clause, re.I) for pattern in pending):
        return True
    # A present-tense dependent clause ("when we announce") is not an
    # assertion that results have been announced. Past declarations stay valid.
    return verb.lower() in {
        "announce", "announces", "announcing", "report", "reports",
        "reporting", "release", "releases",
    } and bool(re.search(
        r"\b(?:when|once|until|before|after)\s+(?:[\w&'-]+\s+){1,4}$",
        clause, re.I,
    ))


def result_context(text: str, *, allow_lexical_variants: bool = False) -> str | None:
    """Keep acquisition stable; matching adds lexical and local modality guards."""
    compact = " ".join(text.split())
    if unsafe_new_event(compact):
        return None
    # Require an actual result event, not just a heading or a cover-date match.
    events = re.compile(
        r"\b(?P<verb>announce(?:s|d)?|report(?:s|ed)?|release(?:s|d)?|reporting|announcing)\b.{0,240}?"
        r"\b(?:(?:financial|quarterly|fiscal|operating|annual)\s+)*results\b",
        re.I,
    )
    offset = 0
    while event := events.search(compact[:6000], offset):
        offset = event.end()
        if allow_lexical_variants:
            prefix = compact[max(0, event.start() - 100):event.start()]
            if _pending_result_trigger(prefix, event.group("verb")):
                # The broad result span may contain a separate actual report.
                # Reject this trigger without swallowing that later assertion.
                offset = event.start() + len(event.group("verb"))
                continue
        context = compact[max(0, event.start() - 100):event.end() + 650]
        if unsafe_new_event(context):
            continue
        if re.search(r"\b(?:quarter|months|full[- ]year|fiscal year)\b", context, re.I):
            tokens = lexical_result_fiscal_tokens if allow_lexical_variants else result_fiscal_tokens
            if result_periods(context) or tokens(context):
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


def lexical_result_fiscal_tokens(context: str) -> frozenset[str]:
    """Matching-only observed variants; acquisition keeps its original vocabulary.

    These tokens describe explicit wording, not event eligibility. Callers must
    still establish actual-result context and preserve all competing tokens.
    Unhyphenated year-before-quarter forms need separate guard review: they can
    bypass acquisition-related holds through a newly recognized primary clause.
    """
    tokens = set(result_fiscal_tokens(context))
    for number, word in enumerate(("first", "second", "third", "fourth"), start=1):
        patterns = (
            rf"\b(\d{{4}})\s+{word}-quarter\b",
            rf"\b{word}-quarter\s+(\d{{4}})\b",
            rf"\b{word}\s+quarter\s+(?:of\s+)?fiscal\s+(\d{{4}})\b",
        )
        for pattern in patterns:
            for year in re.findall(pattern, context, re.I):
                tokens.add(f"{year}:Q{number}")
    for number, year in re.findall(r"\bq([1-4])\s+fiscal\s+(\d{4})\b", context, re.I):
        tokens.add(f"{year}:Q{number}")
    return frozenset(tokens)
