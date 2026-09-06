from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import contract, delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation
from .readers import ParallelModelRepository


def _value(value: Any, digits: int = 2) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def render_company_report(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    market_db: Path,
    output: Path,
) -> Path:
    repository=ParallelModelRepository(conn); repository.assert_v2_bundle()
    score_history=repository.score_history(company_id,model_fingerprint=score.MODEL_FINGERPRINT)
    lifecycle_history=repository.lifecycle_history(company_id,model_fingerprint=lifecycle.MODEL_FINGERPRINT)
    valuation_history=repository.valuation_history(company_id,model_fingerprint=valuation.MODEL_FINGERPRINT)
    delta_history=repository.delta_history(company_id,model_fingerprint=delta.MODEL_FINGERPRINT)
    score_row=score_history[-1] if score_history else None
    life=lifecycle_history[-1] if lifecycle_history else None
    value=valuation_history[-1] if valuation_history else None
    change=delta_history[-1] if delta_history else None
    diagnostics=repository.diagnostic_current(company_id,model_fingerprint=diagnostic_flags.MODEL_FINGERPRINT)
    relative=repository.relative_current(company_id,model_fingerprint=relative_position.MODEL_FINGERPRINT)
    if not score_row or not life or not value: raise LookupError(f"OPERATING_INCOME_V2_REPORT_COMPANY_NOT_FOUND:{company_id}")
    ticker=life.get("ticker") or value.get("ticker") or str(company_id)
    with sqlite3.connect(f"file:{market_db.resolve()}?mode=ro",uri=True) as market:
        price=market.execute("SELECT close,pvm FROM osakedata WHERE osake=? AND close>0 ORDER BY pvm DESC LIMIT 1",(ticker,)).fetchone()
    current_price=float(price[0]) if price else None
    shares=value.get("shares_outstanding"); cash=value.get("cash"); debt=value.get("total_debt"); operating=value.get("ttm_operating_income")
    indicative_yield=None
    if all(item is not None for item in (current_price,shares,cash,debt,operating)):
        ev=current_price*shares+debt-cash
        indicative_yield=operating/ev if ev>0 else None
    lines=[
        f"# {ticker} Operating-Income V2 Snapshot", "",
        f"Package: `{contract.FAMILY_VERSION}` / `{contract.FAMILY_FINGERPRINT}`", "",
        "## Current", "",
        f"- Fundamental Score: {_value(score_row['total_score'])} ({score_row['readiness_status']})",
        f"- Lifecycle: {life.get('final_state') or 'N/A'} ({life['lifecycle_status']}), candidate {life.get('candidate_state') or 'none'}",
        f"- Valuation Score: {_value(value['total_valuation_score'])} ({value['valuation_status']})",
        f"- Operating Income: {_value(value.get('ttm_operating_income'))}",
        f"- Operating Margin: {_value(life.get('operating_margin_ttm',None) * 100 if life.get('operating_margin_ttm') is not None else None)}%",
        f"- Operating Income Yield: {_value(value.get('operating_income_yield',None) * 100 if value.get('operating_income_yield') is not None else None)}%",
        f"- EV / Operating Income: {_value(1/value['operating_income_yield'] if value.get('operating_income_yield') and value['operating_income_yield']>0 else None)}",
        f"- Current-price indicative Operating Income Yield ({price[1] if price else 'N/A'}): {_value(indicative_yield*100 if indicative_yield is not None else None)}%", "",
        "## Score Components", "",
        "| Component | Points |", "|---|---:|",
    ]
    labels={"OPERATING_PROFITABILITY":"Operating Profitability","OPERATING_MARGIN_DIRECTION":"Operating Margin Direction","FUNDAMENTAL_TRAJECTORY":"Fundamental Trajectory (includes Operating Margin Trajectory)"}
    lines.extend(f"| {labels.get(item['component_name'],item['component_name'].replace('_',' ').title())} | {_value(item['component_score'])} |" for item in score_row["components"])
    component_names=tuple(item["component_name"] for item in score_row["components"])
    lines.extend(["", "## Score History", "", "| Quarter | Total | Status | "+" | ".join(labels.get(name,name.replace('_',' ').title()) for name in component_names)+" |", "|---|---:|---|"+"---:|"*len(component_names)])
    for row in score_history:
        by_name={item["component_name"]:item["component_score"] for item in row["components"]}
        lines.append(f"| {row['quarter_id']} | {_value(row['total_score'])} | {row['readiness_status']} | "+" | ".join(_value(by_name.get(name)) for name in component_names)+" |")
    lines.extend(["", "## Lifecycle History", "", "| Quarter | Raw | Final | Status | Candidate | Operating Margin | Operating Margin Direction |", "|---|---|---|---|---|---:|---:|"])
    lines.extend(f"| {row['quarter_id']} | {row['raw_state']} | {row.get('final_state') or 'N/A'} | {row['lifecycle_status']} | {row.get('candidate_state') or 'none'} | {_value(row.get('operating_margin_ttm'))} | {_value(row.get('operating_margin_direction'))} |" for row in lifecycle_history)
    lines.extend(["", "## Valuation History", "", "| Quarter | Score | Status | Operating Income | Operating Income Yield | FCF Yield | Earnings Yield |", "|---|---:|---|---:|---:|---:|---:|"])
    lines.extend(f"| {row['quarter_id']} | {_value(row['total_valuation_score'])} | {row['valuation_status']} | {_value(row.get('ttm_operating_income'))} | {_value(row.get('operating_income_yield'))} | {_value(row.get('fcf_yield'))} | {_value(row.get('earnings_yield'))} |" for row in valuation_history)
    lines.extend(["", "## Delta History", "", "| Fiscal sequence | QoQ | 2Q | YoY |", "|---:|---:|---:|---:|"])
    lines.extend(f"| {row['fiscal_sequence']} | {_value(row.get('qoq_delta'))} | {_value(row.get('two_quarter_delta'))} | {_value(row.get('yoy_delta'))} |" for row in delta_history)
    lines.extend(["", "## Current Delta", "", f"QoQ: {_value(change.get('qoq_delta') if change else None)}; 2Q: {_value(change.get('two_quarter_delta') if change else None)}; YoY: {_value(change.get('yoy_delta') if change else None)}", "", "## Relative Position", "", "| Measure | Scope | Percentile | Status |", "|---|---|---:|---|"])
    lines.extend(f"| {item['measure']} | {item['peer_scope']} | {_value(item['percentile'])} | {item['result_status']} |" for item in relative)
    lines.extend(["", "## Diagnostic Flags", "", "| Flag | Status | Reason |", "|---|---|---|"])
    lines.extend(f"| {item['flag_name']} | {item['status_text']} | {item['reason_text']} |" for item in (diagnostics or {}).get("evaluations",[]))
    lines.extend(["", "## Model Identities", ""])
    lines.extend(f"- {name}: `{version}` / `{fingerprint}`" for name,(version,fingerprint) in (("Score",(score.MODEL_VERSION,score.MODEL_FINGERPRINT)),("Lifecycle",(lifecycle.MODEL_VERSION,lifecycle.MODEL_FINGERPRINT)),("Valuation",(valuation.MODEL_VERSION,valuation.MODEL_FINGERPRINT)),("Delta",(delta.MODEL_VERSION,delta.MODEL_FINGERPRINT)),("Relative Position",(relative_position.MODEL_VERSION,relative_position.MODEL_FINGERPRINT)),("Diagnostic Flags",(diagnostic_flags.MODEL_VERSION,diagnostic_flags.MODEL_FINGERPRINT)),("Snapshot",(snapshot.MODEL_VERSION,snapshot.MODEL_FINGERPRINT))))
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text("\n".join(lines)+"\n",encoding="utf-8"); return output
