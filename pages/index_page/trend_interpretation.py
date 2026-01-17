from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pages.index_page.trend_models import InterpretationItem, TrendChain, TrendSnapshot


def classify_confidence(v: int) -> str:
    """Map numeric confidence to LOW/MID/HIGH."""
    try:
        val = int(v)
    except Exception:
        val = 0
    if val <= 39:
        return "LOW"
    if val <= 59:
        return "MID"
    return "HIGH"


def _level_score(level: str) -> int:
    lvl = (level or "").upper()
    if lvl == "HIGH":
        return 3
    if lvl == "MID":
        return 2
    return 1


def _rel_score(relevance: Optional[str]) -> int:
    if relevance is None:
        return 0
    rel = relevance.upper()
    if rel == "ACTIVE":
        return 3
    if rel == "FADING":
        return 2
    if rel == "HISTORICAL":
        return 1
    return 0


def format_cc_phrase(bias: str, cc_level: str) -> str:
    bias_up = (bias or "").upper() == "UP"
    bias_down = (bias or "").upper() == "DOWN"
    if bias_up:
        if cc_level == "HIGH":
            return "Nykytila on vahva nousuvaihe."
        if cc_level == "MID":
            return "Nykytila viittaa nousuun, mutta signaali ei ole vielä vahva."
        return "Nykytila ei tue selkeää nousua."
    if bias_down:
        if cc_level == "HIGH":
            return "Nykytila on vahva laskuvaihe."
        if cc_level == "MID":
            return "Nykytila viittaa laskuun, mutta signaali on epävarma."
        return "Nykytila ei tue selkeää laskua."
    return "Nykytila on epäselvä tai sivuttaisvaiheessa."


def format_sc_phrase(sc_level: str, relevance: Optional[str]) -> str:
    if relevance is None:
        return "Rakenteellista trendiketjua ei löytynyt tarkastelujaksosta."
    rel = relevance.upper()
    if rel == "ACTIVE":
        if sc_level == "HIGH":
            return "Rakenteellinen trendi on vahva ja edelleen ajankohtainen."
        if sc_level == "MID":
            return "Rakenteellinen trendi on kohtalainen ja edelleen ajankohtainen."
        return "Rakenteellinen trendi on heikko, mutta ajankohtainen."
    if rel == "FADING":
        if sc_level == "HIGH":
            return "Rakenteellinen trendi on vahva, mutta sen ajankohtaisuus heikkenee."
        if sc_level == "MID":
            return "Rakenteellinen trendi on kohtalainen, mutta sen ajankohtaisuus heikkenee."
        return "Rakenteellinen trendi on heikko ja menettää ajankohtaisuuttaan."
    # HISTORICAL tai muu
    if sc_level == "HIGH":
        return "Rakenteellinen trendi on ollut vahva, mutta se on nyt lähinnä historiallinen tausta."
    if sc_level == "MID":
        return "Rakenteellinen trendi on ollut kohtalainen, mutta se on nyt lähinnä historiallinen tausta."
    return "Rakenteellinen trendi ei ole ajankohtainen (vain historiallista taustaa)."


def format_combined_phrase(
    cc_level: str, sc_level: str, relevance: Optional[str]
) -> str:
    if relevance is None:
        if cc_level == "HIGH":
            return "Liike näyttää vahvalta, mutta ilman rakenteellista tukea."
        if cc_level == "MID":
            return "Tilanne on epävarma ja ilman selkeää rakenteellista tukea."
        return "Ei selkeää nykytrendia eikä rakenteellista tukea."

    rel = relevance.upper()
    if rel == "ACTIVE":
        if cc_level == "HIGH" and sc_level == "HIGH":
            return "Vahva ja kypsä trendi – rakenne tukee nykyliikettä."
        if cc_level == "HIGH" and sc_level in ("MID", "LOW"):
            return "Vahva nykyliike, rakenne vasta muodostumassa."
        if cc_level == "LOW" and sc_level == "HIGH":
            return "Pitkä trendi näyttää heikentyvän – riski kasvaa."
        return "Tilanne vaatii varmistusta rakenteen ja nykyliikkeen välillä."
    if rel == "FADING":
        if cc_level == "HIGH" and sc_level == "HIGH":
            return "Vahva nykyliike, mutta rakenteellinen tuki heikkenee."
        if cc_level == "LOW" and sc_level == "HIGH":
            return "Aiemmin vahva trendi, mutta nykytila ei enää tue."
        return "Nykyliike ja rakenne eivät ole täysin linjassa."
    # HISTORICAL
    if cc_level == "HIGH":
        return "Nykyinen liike ilman ajankohtaista rakenteellista tukea."
    if cc_level == "MID":
        return "Epävarma nykytila; historiallinen rakenne ei ohjaa nyt."
    return "Ei selkeää trendiä; rakenne on vain historiallista taustaa."


def _best_chain(
    chains: List[TrendChain], otype: str, oname: str
) -> Optional[TrendChain]:
    filtered = [c for c in chains if c.object_type == otype and c.object_name == oname]
    if not filtered:
        return None
    filtered.sort(key=lambda c: (c.confidence, c.end_date), reverse=True)
    return filtered[0]


@dataclass
class _Metrics:
    otype: str
    oname: str
    bias: str
    cc_level: str
    cc_score: int
    sc_level: str
    sc_score: int
    relevance: Optional[str]
    rel_score: int
    combo: str


def _relative_sentence(
    child: _Metrics,
    parent: _Metrics,
    *,
    child_label: str,
    parent_label: str,
    child_is_stock: bool = False,
) -> str:
    """
    Build one sentence that compares child vs parent using:
    - structural context: sc_score + relevance score
    - current context: cc_score
    Additionally for stocks: mention if bias diverges from context (when CC is at least MID).
    """
    # 1A) Structural leadership
    struct_lead = None
    if (child.sc_score >= parent.sc_score + 1) and (
        child.rel_score >= parent.rel_score
    ):
        struct_lead = f"{child_label} johtaa {parent_label}a rakenteellisesti"
    elif (child.sc_score <= parent.sc_score - 1) or (
        child.rel_score < parent.rel_score
    ):
        struct_lead = f"{child_label} jää {parent_label}n rakenteesta jälkeen"
    else:
        struct_lead = f"{child_label}n rakenne on linjassa {parent_label}n kanssa"

    # 1B) Current momentum
    if child.cc_score >= parent.cc_score + 1:
        cur = "nykyliike on kontekstia vahvempi"
    elif child.cc_score <= parent.cc_score - 1:
        cur = "nykyliike on kontekstia heikompi"
    else:
        cur = "nykyliike on kontekstin kaltainen"

    sent = f"{struct_lead}, ja {cur}."

    # Stock-specific: diverging bias (optional add-on, still keeps single sentence by appending clause)
    if child_is_stock:
        b_child = (child.bias or "").upper()
        b_parent = (parent.bias or "").upper()
        if (
            b_child in ("UP", "DOWN")
            and b_parent in ("UP", "DOWN")
            and b_child != b_parent
            and child.cc_score >= 2
        ):
            # append short clause
            sent = sent[:-1] + " (liikkuu vasten kontekstia)."

    return sent


def _get_metrics(
    snap_map: Dict[Tuple[str, str], TrendSnapshot],
    chains: List[TrendChain],
    otype: str,
    oname: str,
) -> Optional[_Metrics]:
    snap = snap_map.get((otype, oname))
    if not snap:
        return None

    cc_level = classify_confidence(snap.confidence)
    cc_score = _level_score(cc_level)

    chain = _best_chain(chains, otype, oname)
    if chain:
        sc_level = classify_confidence(chain.confidence)
        relevance = getattr(chain, "relevance", None)
    else:
        sc_level = "LOW"
        relevance = None

    sc_score = _level_score(sc_level)
    rel_score = _rel_score(relevance)
    combo = format_combined_phrase(cc_level, sc_level, relevance)

    return _Metrics(
        otype=otype,
        oname=oname,
        bias=snap.bias,
        cc_level=cc_level,
        cc_score=cc_score,
        sc_level=sc_level,
        sc_score=sc_score,
        relevance=relevance,
        rel_score=rel_score,
        combo=combo,
    )


def build_interpretation_items(
    snapshots: List[TrendSnapshot],
    chains: List[TrendChain],
    plotted_objects: List[Tuple[str, str]],
    stock_sector: Optional[str] = None,
) -> List[InterpretationItem]:
    """
    Build interpretation items for plotted objects.

    Rules:
    - MARKET: 3 parts: CC phrase + SC phrase + combined phrase (as before).
    - SECTOR: 2–3 sentences:
        1) Markkina: <market_combo>
        2) Sektori: <sector_combo>
        3) Relative Context sentence (sector vs market)
    - STOCK: always compare to sector first (as requested):
        1) Sektori: <sector_combo>   (if sector metrics available, else Markkina: <market_combo>)
        2) Osake: <stock_combo>
        3) Relative Context sentence (stock vs sector if possible; else vs market)
      Optionally append sector name info only if it doesn't inflate text too much.
    """
    snap_map: Dict[Tuple[str, str], TrendSnapshot] = {
        (s.object_type, s.object_name): s for s in snapshots
    }

    # Market metrics (for context), even if market isn't plotted
    mkt = _get_metrics(snap_map, chains, "MARKET", "MARKET")

    # Sector metrics cache for quick lookups
    sector_metrics_by_name: Dict[str, _Metrics] = {}
    for otype, oname in plotted_objects:
        if otype == "SECTOR":
            met = _get_metrics(snap_map, chains, "SECTOR", oname)
            if met:
                sector_metrics_by_name[oname] = met

    items: List[InterpretationItem] = []

    def _market_full_text(m: _Metrics) -> str:
        cc_phrase = format_cc_phrase(m.bias, m.cc_level)
        sc_phrase = format_sc_phrase(m.sc_level, m.relevance)
        return " ".join([cc_phrase, sc_phrase, m.combo])

    market_combo = mkt.combo if mkt else "Markkinadata puuttuu."

    for otype, oname in plotted_objects:
        if otype == "MARKET":
            if mkt:
                items.append(
                    InterpretationItem("MARKET", "MARKET", _market_full_text(mkt))
                )
            else:
                items.append(
                    InterpretationItem("MARKET", "MARKET", "Markkinadata puuttuu.")
                )
            continue

        if otype == "SECTOR":
            sec = sector_metrics_by_name.get(oname) or _get_metrics(
                snap_map, chains, "SECTOR", oname
            )
            if not sec:
                continue

            # Relative sentence: sector vs market if market exists; otherwise omit.
            rel_sent = ""
            if mkt:
                rel_sent = _relative_sentence(
                    child=sec,
                    parent=mkt,
                    child_label="Sektori",
                    parent_label="markkina",
                    child_is_stock=False,
                )

            parts = [
                f"Markkina: {market_combo}",
                f"Sektori: {sec.combo}",
            ]
            if rel_sent:
                parts.append(rel_sent)
            text = " ".join(parts)
            items.append(InterpretationItem("SECTOR", oname, text))
            continue

        if otype == "STOCK":
            stk = _get_metrics(snap_map, chains, "STOCK", oname)
            if not stk:
                continue

            # Always compare stock to sector first (if we can resolve sector metrics).
            # We try:
            # 1) stock_sector argument -> find that sector in plotted sectors
            # 2) if not found, fall back to market
            parent = None
            parent_label = ""
            header = ""

            if stock_sector and stock_sector in sector_metrics_by_name:
                parent = sector_metrics_by_name[stock_sector]
                parent_label = "sektoria"
                header = f"Sektori: {parent.combo}"
            elif mkt:
                parent = mkt
                parent_label = "markkinaa"
                header = f"Markkina: {market_combo}"
            else:
                parent = None
                header = "Konteksti: -"

            parts = [header, f"Osake: {stk.combo}"]

            if parent:
                rel_sent = _relative_sentence(
                    child=stk,
                    parent=parent,
                    child_label="Osake",
                    parent_label=parent_label,
                    child_is_stock=True,
                )
                parts.append(rel_sent)

            # Optional: add sector name label (short)
            if stock_sector:
                parts.append(f"(Sektori: {stock_sector})")

            # Keep it readable; joins into 2–3 sentences + optional parenthetical.
            text = " ".join(parts)
            items.append(InterpretationItem("STOCK", oname, text))
            continue

    return items
