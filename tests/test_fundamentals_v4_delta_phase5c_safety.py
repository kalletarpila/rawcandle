from __future__ import annotations

from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_delta_phase5c import build_parser
from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.phase5c import validate_request
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FP
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_FP
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_FP


def paths(tmp_path):
    values=[]
    for name in ("analysis","canonical","provider","market","taxonomy"):
        path=(tmp_path/f"{name}.db").resolve(); path.touch(); values.append(path)
    return values


def request(tmp_path,destination,**changes):
    analysis,canonical,provider,market,taxonomy=paths(tmp_path)
    values=dict(analysis_db=analysis,canonical_db=canonical,provider_db=provider,market_db=market,taxonomy_db=taxonomy,destination=destination,score_model_fingerprint=SCORE_FP,lifecycle_model_fingerprint=LIFECYCLE_FP,valuation_model_fingerprint=VALUATION_FP,delta_model_fingerprint=MODEL_FINGERPRINT,full_universe=True,company_ids=(),apply=False)
    values.update(changes); return values


def test_cli_defaults_to_dry_run_and_requires_destination_and_scope():
    parser=build_parser(); actions={action.dest:action for action in parser._actions}
    assert actions["apply"].default is False
    assert actions["destination"].required is True
    assert not hasattr(actions["full_universe"],"confirm_production")


def test_production_source_symlink_normalized_and_backup_destinations_rejected(tmp_path):
    source=tmp_path/"source.db"; source.touch()
    kwargs=request(tmp_path,source.resolve())
    kwargs["analysis_db"]=source.resolve()
    with pytest.raises(PermissionError,match="SOURCE_DATABASE"): validate_request(**kwargs)
    link=tmp_path/"link.db"; link.symlink_to(source)
    with pytest.raises(PermissionError,match="SYMLINK"): validate_request(**request(tmp_path,link.resolve().parent/"link.db"))
    production=Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db")
    with pytest.raises(PermissionError,match="PRODUCTION"): validate_request(**request(tmp_path,production))
    backup=Path("/home/kalle/projects/rawcandle/backups/phase5c-test.db")
    with pytest.raises(PermissionError,match="BACKUP"): validate_request(**request(tmp_path,backup))


def test_exactly_one_scope_and_locked_fingerprint_required(tmp_path):
    destination=(tmp_path/"dest.db").resolve()
    with pytest.raises(ValueError,match="ONE_SCOPE"): validate_request(**request(tmp_path,destination,full_universe=False,company_ids=()))
    with pytest.raises(ValueError,match="ONE_SCOPE"): validate_request(**request(tmp_path,destination,full_universe=True,company_ids=(1,)))
    with pytest.raises(ValueError,match="DELTA_MODEL"): validate_request(**request(tmp_path,destination,delta_model_fingerprint="wrong"))
