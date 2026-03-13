from analysis.divergence_v1 import (
    bearish_overbought_score,
    bullish_oversold_score,
    clamp01,
    compute_bearish_candidate_strength,
    compute_bullish_candidate_strength,
    is_rolling_high_candidate,
    is_rolling_low_candidate,
)


def test_clamp01_limits_values():
    assert clamp01(-1.0) == 0.0
    assert clamp01(0.5) == 0.5
    assert clamp01(2.0) == 1.0


def test_rolling_candidates_use_trailing_window_only():
    closes = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 100]

    assert is_rolling_low_candidate(closes, 9) is True
    assert is_rolling_high_candidate(closes, 9) is False
    assert is_rolling_high_candidate(closes, 10) is True


def test_bullish_strength_skips_non_positive_prices():
    assert compute_bullish_candidate_strength(0.0, 10.0, 20.0, 30.0) == 0.0
    assert compute_bullish_candidate_strength(10.0, 0.0, 20.0, 30.0) == 0.0


def test_bearish_strength_skips_non_positive_prices():
    assert compute_bearish_candidate_strength(0.0, 10.0, 80.0, 60.0) == 0.0
    assert compute_bearish_candidate_strength(10.0, 0.0, 80.0, 60.0) == 0.0


def test_bullish_oversold_score_steps():
    assert bullish_oversold_score(25.0) == 1.0
    assert bullish_oversold_score(34.0) == 0.7
    assert bullish_oversold_score(38.0) == 0.4
    assert bullish_oversold_score(50.0) == 0.1


def test_bearish_overbought_score_steps():
    assert bearish_overbought_score(75.0) == 1.0
    assert bearish_overbought_score(67.0) == 0.7
    assert bearish_overbought_score(62.0) == 0.4
    assert bearish_overbought_score(50.0) == 0.1


def test_compute_bullish_candidate_strength_exact_numeric_output():
    strength = compute_bullish_candidate_strength(
        close_p=100.0,
        close_t=96.0,
        rsi_p=20.0,
        rsi_t=25.0,
    )

    assert strength == 0.55


def test_compute_bearish_candidate_strength_exact_numeric_output():
    strength = compute_bearish_candidate_strength(
        close_p=100.0,
        close_t=104.0,
        rsi_p=75.0,
        rsi_t=70.0,
    )

    assert strength == 0.55
