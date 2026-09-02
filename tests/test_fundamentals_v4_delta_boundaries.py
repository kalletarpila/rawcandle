from __future__ import annotations

from rawcandle.cli.run_fundamentals_v4_delta_rehearsal import build_parser
from rawcandle.fundamentals.delta import engine


def test_cli_has_no_apply_or_production_writer_path():
    destinations = {action.dest for action in build_parser()._actions}
    assert "apply" not in destinations
    assert "production_db" not in destinations


def test_model_contract_excludes_combined_score_relative_position_and_taxonomy_delta():
    serialized = str(engine.MODEL_CONTRACT)
    assert "Relative Position" not in serialized
    assert "taxonomy" not in serialized.lower()
    assert "combined_delta_score" not in serialized.lower()
    assert engine.MODEL_CONTRACT["semantic_mode"] == "CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA"
