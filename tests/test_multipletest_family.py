"""Multiple-testing register tests (plan tasks 6, 6.1, 6.2; §D.2).

Covers: the FIVE canonical staking schemes match config/baseline.yaml
byte-for-byte (task 4.1 -- a four-vs-five mismatch corrupts the K denominator);
the headline family menu, K formula, and abandoned-cell counting are present;
the WC stratification (K_WC) is enumerated as the BH-FDR exploratory layer that
cannot upgrade the headline; the cross-pillar WC-test inventory checklist
(task 6.1) covers the EDGE §7 items 1-4 and the STAT §10 checks; and the
Deflated-Sharpe N_eff rule is pinned to conservative raw-N (task 6.2).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FAMILY = PROJECT_ROOT / "config" / "multipletest_family.yaml"
BASELINE = PROJECT_ROOT / "config" / "baseline.yaml"
POWER_RECORD = PROJECT_ROOT / "docs" / "protocol" / "power_H001-wc-underdog-dnb.md"

# The five canonical schemes (methodology.md §1.2; STAKE §2/§7.1). Order matters:
# the two files must agree byte-for-byte, including level_to_odds (dropped in
# ARCH §3.3 -- plan task 4.1 restores it).
CANONICAL_SCHEMES = ["flat", "fixed_fraction", "level_to_odds", "kelly", "fractional_kelly"]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_register_file_exists_and_parses():
    assert FAMILY.exists()
    reg = _load(FAMILY)
    assert reg["frozen_before_wc"] is True


def test_five_staking_schemes_match_baseline_byte_for_byte():
    reg = _load(FAMILY)
    base = _load(BASELINE)
    family_schemes = reg["headline_family"]["dimensions"]["staking_scheme"]["values"]
    baseline_schemes = base["staking"]["schemes"]
    assert family_schemes == CANONICAL_SCHEMES, "register must list the five canonical schemes"
    assert baseline_schemes == CANONICAL_SCHEMES, "baseline must list the five canonical schemes"
    # The load-bearing cross-file invariant (task 4.1).
    assert family_schemes == baseline_schemes
    assert reg["headline_family"]["dimensions"]["staking_scheme"]["cardinality"] == 5


def test_level_to_odds_is_present_not_dropped():
    # ARCH §3.3 lists only four; the register/baseline must include level_to_odds.
    assert (
        "level_to_odds"
        in _load(FAMILY)["headline_family"]["dimensions"]["staking_scheme"]["values"]
    )
    assert "level_to_odds" in _load(BASELINE)["staking"]["schemes"]


def test_headline_family_counts_abandoned_cells_and_has_k_formula():
    hf = _load(FAMILY)["headline_family"]
    assert hf["count_abandoned_cells"] is True  # STAT Open Question 8
    assert hf["K_formula"]
    # The resolved-cardinality factor side(2)*staking(5)*devig(1)*odds_source(2) = 20.
    assert hf["K_base_multiplier"] == 20
    # K stays null until the tau grid resolves (no hand-set integer; §D.3).
    assert hf["K"] is None


def test_devig_is_frozen_a_priori_not_in_k():
    devig = _load(FAMILY)["headline_family"]["dimensions"]["devig_method"]
    assert devig["primary"] == "shin"
    assert devig["selected_per_fold"] is False
    assert devig["cardinality_in_k"] == 1  # does NOT multiply K (CALC §4.6)
    # The same primary must be pinned in baseline.yaml odds.devig_method.
    assert _load(BASELINE)["odds"]["devig_method"] == "shin"


def test_wc_stratification_is_bh_fdr_exploratory_and_cannot_upgrade_headline():
    wc = _load(FAMILY)["wc_stratification"]
    assert wc["decision"] == "exploratory_bh_fdr"
    assert wc["cannot_upgrade_headline"] is True
    dims = wc["dimensions"]
    for d in ("stage", "host", "dead_rubber"):
        assert dims[d]["cardinality"] == 2
    # odds_bucket is empirical-quantile cut, so its grid is null (no magic number).
    assert dims["odds_bucket"]["grid"] is None
    # K_WC = 8 * n_odds_buckets; concrete integer pinned later, before fitting.
    assert wc["K_WC_base_multiplier"] == 8
    assert wc["K_WC"] is None


def test_power_record_does_not_pin_concrete_kwc_while_register_kwc_is_null():
    """The frozen power record must mirror the register's SYMBOLIC K_WC.

    The register leaves K_WC null (= 8 * n_odds_buckets) because the odds-bucket
    count is an empirical-quantile cut resolved only in Phase 1 (DATA §8;
    no-magic-number). So long as the register's K_WC is null, power_<HID>.md may
    NOT pin a concrete integer K_WC -- a frozen pre-data artifact asserting a
    magic-number stratum count is a pre-registration-integrity defect. The
    authoritative symbolic form is `K_WC = 8 x n_odds_buckets`.
    """
    reg = _load(FAMILY)
    # Guard: this invariant only binds while the register itself is unresolved.
    if reg["wc_stratification"]["K_WC"] is not None:
        return
    assert POWER_RECORD.exists(), "power record must exist for the consistency check"
    text = POWER_RECORD.read_text(encoding="utf-8")

    # The symbolic form must be present (matches the register's 8 * n_odds_buckets).
    # U+00D7 is the MULTIPLICATION SIGN used in the record's prose; reference it by
    # codepoint to avoid the ambiguous literal glyph in source (ruff RUF001).
    times = "\u00d7"  # MULTIPLICATION SIGN, the exact glyph the record's prose uses
    mult = rf"[x{times}*]"
    assert "n_odds_buckets" in text, "power record must carry the symbolic n_odds_buckets count"
    assert re.search(rf"8\s*{mult}\s*n_odds_buckets", text), (
        "power record must restate K_WC = 8 x n_odds_buckets symbolically"
    )

    # No concrete integer K_WC may be pinned. Catch any 'K_WC = <int>' assignment
    # (e.g. the old 'K_WC = 24') but NOT the symbolic base multiplier in
    # 'K_WC = 8 x n_odds_buckets' (the 8 there is followed by the symbolic factor,
    # so it is not a pinned cardinality). The negative lookahead excludes an int
    # immediately multiplied into n_odds_buckets.
    pinned = re.findall(rf"K_WC\s*=\s*([0-9][0-9,]*)\b(?!\s*{mult}\s*n_odds_buckets)", text)
    assert not pinned, (
        f"power record pins concrete K_WC integer(s) {pinned} while register K_WC is null"
    )
    # The specific rejected magic-number product/value must be absent. Reuse the
    # codepoint-built `times` glyph above (the exact glyph the record's prose uses).
    rejected_product = f"3 {times} 2 {times} 2 {times} 2"
    assert rejected_product not in text, "magic-number odds-bucket=3 product must be removed"
    assert "= 24" not in text, "the asserted K_WC = 24 must be removed"


def test_dead_rubber_headline_confined_to_32_team_block():
    dr = _load(FAMILY)["wc_stratification"]["dimensions"]["dead_rubber"]
    assert "2002-2022" in dr["headline_block"]
    assert "2026" in dr["descriptive_only_block"]


def test_cross_pillar_inventory_covers_edge_items_and_stat_checks():
    inv = _load(FAMILY)["wc_test_inventory"]
    ids = {row["id"] for row in inv}
    # EDGE §7 primary-diagnostic ranking items 1-4 must each be a row (task 6.1).
    for edge_id in ("EDGE-7-1", "EDGE-7-2", "EDGE-7-3", "EDGE-7-4"):
        assert edge_id in ids, f"cross-pillar checklist missing {edge_id}"
    # The STAT §10 assumption checks must be present and declared non-inferential.
    stat10 = next(r for r in inv if r["id"] == "STAT-10")
    assert stat10["inferential"] is False
    assert stat10["correction_layer"] == "none"
    # The CLV and loss-gradient tests are inferential and BH-FDR-corrected.
    clv = next(r for r in inv if r["id"] == "EDGE-7-1")
    assert clv["inferential"] is True
    assert clv["correction_layer"] == "bh_fdr_exploratory"
    gradient = next(r for r in inv if r["id"] == "EDGE-7-2")
    assert gradient["inferential"] is True


def test_every_inferential_test_maps_to_a_kwc_cell_or_is_declared_descriptor():
    # Task 6.1 invariant: a WC-touching test is EITHER mapped to a K_WC cell OR
    # explicitly declared non-inferential (maps_to_kwc_cell null).
    for row in _load(FAMILY)["wc_test_inventory"]:
        if row["inferential"]:
            assert row["maps_to_kwc_cell"] is not None, f"{row['id']} inferential but unmapped"
        else:
            assert row["maps_to_kwc_cell"] is None


def test_deflated_sharpe_neff_pinned_conservative_raw_n():
    dsr = _load(FAMILY)["deflated_sharpe"]
    assert dsr["N_eff_rule"] == "conservative_raw_N"  # task 6.2
    assert dsr["N_eff_equals"] == "K"
    assert dsr["dsr_is_lower_bound_on_significance"] is True
    assert dsr["hac_inflated_denominator"] is True
    # An estimated N_eff is NOT adopted (would need a single pre-registered rule).
    assert dsr["alternative_if_estimated"]["permitted"] is False


def test_corrections_hansen_default_white_crosscheck_bh_exploratory():
    corr = _load(FAMILY)["corrections"]
    assert corr["headline"]["primary"] == "hansen_spa"  # default
    assert corr["headline"]["cross_check"] == "white_reality_check"
    assert corr["exploratory"]["method"] == "benjamini_hochberg"
    assert corr["exploratory"]["cannot_upgrade_headline"] is True


def test_cv_is_walk_forward_with_wc_held_out():
    cv = _load(FAMILY)["cv"]
    assert cv["scheme"] == "walk_forward"  # never k-fold
    assert cv["held_out_test_block"] == "fifa_world_cup"
    # de-vig is frozen a priori, not per-fold selected.
    assert "devig_method" in cv["frozen_a_priori_not_selected"]
    assert "devig_method" not in cv["selected_per_fold"]


def test_near_tie_branch_matches_frozen_design_swept_band():
    """The near-tie branch in BOTH configs must encode the SWEPT coin-flip band
    that design.md §3/§5 freezes -- not the strict-tie branch design.md rejects.

    design.md is immutable; the configs are corrected to it (Phase-0 acceptance:
    "near-tie band registered iff searched"; "the two specs must not disagree once
    config/ freezes"). The swept branch => near_tie_band.included_in_k is true,
    tau_tie is in cv.selected_per_fold and K = 20 * n_tau * n_tau_tie in the
    register, and require_strict_underdog is cleared (false) in baseline.yaml. The
    strict-tie config silently under-counted K (20 * n_tau), under-correcting
    White RC / Hansen SPA and inflating the DSR E[max SR] gate.
    """
    reg = _load(FAMILY)
    base = _load(BASELINE)

    near_tie = reg["headline_family"]["dimensions"]["near_tie_band"]
    # Swept band frozen in design.md §3 -> counted in K.
    assert near_tie["included_in_k"] is True, "design.md §3 freezes the swept band -> included_in_k"
    assert near_tie["cardinality_symbol"] == "n_tau_tie"
    # No-magic-number: the grid stays null until the §D.3 sweep resolves it.
    assert near_tie["grid"] is None

    # design.md §5 out-of-fold selection set = {tau, phi, c, lambda, tau_tie}.
    selected = reg["cv"]["selected_per_fold"]
    assert "tau_tie" in selected, "design.md §5 puts tau_tie in the out-of-fold selection set"
    assert set(selected) == {"tau", "phi", "c", "lambda", "tau_tie"}

    # K must carry the n_tau_tie factor (20 * n_tau * n_tau_tie, not 20 * n_tau).
    k_formula = reg["headline_family"]["K_formula"]
    assert "n_tau_tie" in k_formula, "K must multiply by n_tau_tie under the swept branch"
    assert "[n_tau_tie?]" not in k_formula, (
        "the conditional placeholder must be resolved to the swept branch"
    )

    # baseline.yaml must clear the strict-tie flag design.md rejects; min_price_gap
    # stays null (resolved by the §D.3 sweep, no-magic-number).
    assert base["selection"]["require_strict_underdog"] is False, (
        "design.md §3 rejects the strict-tie branch -> require_strict_underdog must be false"
    )
    assert base["selection"]["min_price_gap"] is None
