"""Phase 1 ingest unit tests (plan tasks 1, 2, 2.1, 3, 3.1, 8, 9, 9.1).

These tests run OFFLINE: they exercise the validation / refC-derivation / margin-
wedge / open->close / provenance-register logic against a controlled raw_dir seeded
from the committed synthetic fixture (tests/fixtures/mini_league.csv -- the ONLY
synthetic file, used for tests only, never the analysis panel). Network ingestion
itself is covered by the live --stage ingest run, not the unit suite.
"""

from __future__ import annotations

import json

import pytest
from src import ingest, run

FIXTURE = run.PROJECT_ROOT / "tests" / "fixtures" / "mini_league.csv"


def _seed_raw(raw_dir, seasons):
    """Copy the fixture into raw_dir under each <season>_E0.csv name (LF + sha256)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    body = FIXTURE.read_bytes()
    for s in seasons:
        ingest.write_with_sha256(raw_dir / f"{s:04d}_E0.csv", body)


def _cfg(seasons):
    cfg = run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")
    cfg["ingest"]["seasons"] = list(seasons)
    cfg["ingest"]["divisions"] = ["E0"]
    return cfg


# --- checksum / LF helpers --------------------------------------------------


def test_sha256_is_lf_normalized():
    crlf = b"a,b\r\n1,2\r\n"
    lf = b"a,b\n1,2\n"
    assert ingest.sha256_bytes_lf(crlf) == ingest.sha256_bytes_lf(lf)


def test_write_with_sha256_writes_lf_sidecar(tmp_path):
    p, digest = ingest.write_with_sha256(tmp_path / "x.csv", b"a,b\r\n1,2\r\n")
    assert p.read_bytes() == b"a,b\n1,2\n"  # CRLF normalized to LF on disk
    sidecar = p.with_name("x.csv.sha256")
    assert sidecar.read_text(encoding="utf-8").strip().split()[0] == digest


# --- schema validation + no-silent-drops ------------------------------------


def test_validate_file_logs_dropped_rows_with_reason(tmp_path):
    bad = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSCH,PSCD,PSCA,AHCh,PCAHH,PCAHA\n"
        "E0,01/01/24,A,B,2,1,H,2.0,3.4,3.8,0.0,1.95,1.95\n"  # valid
        "E0,02/01/24,C,D,x,1,A,2.0,3.4,3.8,0.0,1.95,1.95\n"  # nonnumeric goals
        "E0,03/01/24,E,F,1,1,X,2.0,3.4,3.8,0.0,1.95,1.95\n"  # invalid FTR
    )
    (tmp_path / "2324_E0.csv").write_text(bad, encoding="utf-8", newline="\n")
    vf = ingest.validate_file(tmp_path / "2324_E0.csv", 2324, "E0")
    assert vf.n_raw == 3
    assert len(vf.df) == 1  # only the valid row survives
    reasons = {d.reason for d in vf.dropped}
    assert "nonnumeric_or_missing_goals" in reasons
    assert "invalid_FTR" in reasons


def test_quoted_ah_code_is_pcahh_pcaha_resolved_from_live_header():
    # The pinned code (config) is PCAHH/PCAHA, resolved against the live 2526/E0
    # header (plan task 2.1). The fixture header carries exactly these columns.
    cfg = run.load_config(run.PROJECT_ROOT / "config" / "baseline.yaml")
    ah = cfg["ingest"]["quoted_ah_pinnacle_close"]
    assert ah["home"] == "PCAHH"
    assert ah["away"] == "PCAHA"
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "PCAHH" in header and "PCAHA" in header


def test_quoted_ah_missing_flag_when_code_absent(tmp_path):
    # A file WITHOUT the pinned AH code: every row is flagged quoted_ah_missing
    # (fail-closed, no silent synthetic fallback; plan task 2.1).
    no_ah = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSCH,PSCD,PSCA\n"
        "E0,01/01/24,A,B,2,1,H,2.0,3.4,3.8\n"
    )
    (tmp_path / "2324_E0.csv").write_text(no_ah, encoding="utf-8", newline="\n")
    vf = ingest.validate_file(tmp_path / "2324_E0.csv", 2324, "E0")
    assert vf.quoted_ah_present_in_header is False
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=2526,
        reference_columns={"pinnacle_close": ["PSCH", "PSCD", "PSCA"]},
        ah_home="PCAHH",
        ah_away="PCAHA",
        ah_line="AHCh",
    )
    assert bool(vf.df["quoted_ah_missing"].all())


# --- season-conditional refC + ref_book -------------------------------------


def test_refc_is_pinnacle_pre_cutover(tmp_path):
    vf = ingest.validate_file(FIXTURE, 2425, "E0")
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=2526,
        reference_columns={
            "pinnacle_close": ["PSCH", "PSCD", "PSCA"],
            "market_avg_close": ["AvgCH", "AvgCD", "AvgCA"],
        },
        ah_home="PCAHH",
        ah_away="PCAHA",
        ah_line="AHCh",
    )
    assert (vf.df["ref_book"] == "pinnacle_close").all()
    # refC_* equals PSC* pre-cutover
    assert vf.df["refC_H"].iloc[0] == pytest.approx(2.95)


def test_refc_falls_back_to_avg_post_cutover(tmp_path):
    # Post-cutover file with PSC* present but AvgC* the intended reference. The
    # fixture has no AvgC* columns, so post-cutover with only PSC* present should
    # report none_available for the avg/max/bfe order (PSC* is NOT used post-cutover).
    body = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,AHCh,PCAHH,PCAHA\n"
        "E0,01/08/25,A,B,1,0,H,2.0,3.4,3.8,2.05,3.45,3.7,0.0,1.95,1.95\n"
    )
    (tmp_path / "2526_E0.csv").write_text(body, encoding="utf-8", newline="\n")
    vf = ingest.validate_file(tmp_path / "2526_E0.csv", 2526, "E0")
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=2526,
        reference_columns={
            "pinnacle_close": ["PSCH", "PSCD", "PSCA"],
            "market_avg_close": ["AvgCH", "AvgCD", "AvgCA"],
        },
        ah_home="PCAHH",
        ah_away="PCAHA",
        ah_line="AHCh",
    )
    assert (vf.df["ref_book"] == "market_avg_close").all()
    assert vf.df["refC_H"].iloc[0] == pytest.approx(2.05)  # AvgCH, not PSCH


# --- underdog + synthetic DNB identity --------------------------------------


def test_underdog_side_and_synthetic_dnb_identity():
    vf = ingest.validate_file(FIXTURE, 2223, "E0")
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=2526,
        reference_columns={"pinnacle_close": ["PSCH", "PSCD", "PSCA"]},
        ah_home="PCAHH",
        ah_away="PCAHA",
        ah_line="AHCh",
    )
    # Row 0: Crystal Palace 2.95 / 3.35 / 2.55 -> home is the higher price = underdog.
    r0 = vf.df.iloc[0]
    assert r0["underdog_side"] == "home"
    # o_DNB = 2.95 * (3.35 - 1)/3.35
    assert r0["o_dnb_underdog"] == pytest.approx(2.95 * (3.35 - 1) / 3.35, rel=1e-9)


# --- margin wedge (task 9) ---------------------------------------------------


def test_margin_wedge_on_ah0_rows():
    vf = ingest.validate_file(FIXTURE, 2223, "E0")
    vf = ingest.attach_reference_price(
        vf,
        cutover_season=2526,
        reference_columns={"pinnacle_close": ["PSCH", "PSCD", "PSCA"]},
        ah_home="PCAHH",
        ah_away="PCAHA",
        ah_line="AHCh",
    )
    panel = ingest.assemble_panel([vf])
    w = ingest.margin_wedge(panel)
    # The fixture has several AHCh == 0.0 rows with PCAHH/PCAHA present.
    assert w["n_both"] >= 1
    # The wedge M_1X2 - M_AH is computed and finite on the overlapping rows. The
    # SIGN of the wedge (1X2 margin exceeding the AH-0.0 margin -- CALC §3.5) is a
    # real-data empirical finding reported from the live ingest, not a property of
    # the hand-written fixture's synthetic AH prices, so it is not asserted here.
    assert w["wedge_mean"] == pytest.approx(w["M_1X2_mean"] - w["M_AH_mean"], abs=1e-6)
    assert "by_division_season" in w


# --- end-to-end offline run (fetch=False over the seeded raw_dir) -----------


def test_run_ingest_offline_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    _seed_raw(raw, [2425, 2526])
    cfg = _cfg([2425, 2526])
    res = ingest.run_ingest(
        cfg,
        run_id="test-offline",
        raw_dir=raw,
        processed_dir=tmp_path / "processed",
        logs_dir=tmp_path / "logs",
        provenance_dir=tmp_path / "raw" / "provenance",
        fetch=False,
        write_parquet=True,
    )
    assert not res.panel.empty
    assert res.panel_path is not None and res.panel_path.exists()
    # dataset_checksums carries every raw CSV + the canonicalized panel.
    assert "2425_E0.csv" in res.dataset_checksums
    assert "league_panel.parquet" in res.dataset_checksums
    # data-quality report written, drop log written.
    dq = json.loads(res.data_quality_path.read_text(encoding="utf-8"))
    assert dq["data_vendor"] == "football-data.co.uk"
    assert dq["quoted_ah_pinnacle_close_code"]["home"] == "PCAHH"
    assert "coverage" in dq and "margin_wedge" in dq and "open_close_moves" in dq
    assert res.drop_log_path.exists()


def test_provenance_register_has_no_accessed_field():
    """REGRESSION (major Phase-1 finding): the wall-clock fetch time must NOT be a
    field of the immutable register whose SHA is pinned into the ingest ReproLog.

    Built offline (fetch=False) over an empty provenance dir, the register carries
    only immutable CONTENT keys -- never 'accessed' -- so its SHA is a function of
    the source bytes / gate result, not of when the gate ran."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        prov = Path(td) / "provenance"
        register = ingest.build_provenance_register(
            raw_dir=Path(td), provenance_dir=prov, cutover_season=2526, fetch=False
        )
    assert "accessed" not in register
    assert set(register) >= {
        "register_type",
        "plan_task",
        "sources",
        "notice",
        "psc_staleness_confirmation",
        "gate_passed",
    }


def test_register_sha_invariant_to_accessed_timestamp(tmp_path):
    """REGRESSION (major Phase-1 finding): the pinned register SHA must be invariant
    to the mutable fetch timestamp.

    Writing identical register CONTENT twice with two different 'accessed' times must
    yield the SAME register SHA (the gate-artifact fingerprint two reviewers agree
    on), while the sibling provenance.json -- which is NOT part of the pinned SHA --
    records the differing fetch time honestly."""
    prov = tmp_path / "provenance"
    register = ingest.build_provenance_register(
        raw_dir=tmp_path, provenance_dir=prov, cutover_season=2526, fetch=False
    )
    out_a, sha_a = ingest.write_provenance_register(
        register, provenance_dir=prov, accessed="2026-06-16T00:00:00+00:00"
    )
    sidecar = prov / "pinnacle_degradation_provenance.json"
    meta_a = json.loads(sidecar.read_text(encoding="utf-8"))
    out_b, sha_b = ingest.write_provenance_register(
        register, provenance_dir=prov, accessed="2027-01-01T12:34:56+00:00"
    )
    meta_b = json.loads(sidecar.read_text(encoding="utf-8"))
    # The pinned register SHA is identical across the two fetch times.
    assert sha_a == sha_b
    assert out_a == out_b
    # The register file itself contains no fetch timestamp.
    assert "accessed" not in json.loads(out_a.read_text(encoding="utf-8"))
    # The mutable fetch time IS recorded out-of-band (provenance, not a pinned key)
    # and differs across runs, back-referencing the register SHA it accompanies.
    assert meta_a["accessed"] != meta_b["accessed"]
    assert meta_a["register_sha256"] == sha_a == meta_b["register_sha256"]


def test_parquet_checksum_is_content_stable(tmp_path):
    raw = tmp_path / "raw"
    _seed_raw(raw, [2223])
    cfg = _cfg([2223])
    kw = dict(
        raw_dir=raw,
        processed_dir=tmp_path / "processed",
        logs_dir=tmp_path / "logs",
        provenance_dir=tmp_path / "raw" / "provenance",
        fetch=False,
    )
    a = ingest.run_ingest(cfg, run_id="a", **kw)
    b = ingest.run_ingest(cfg, run_id="b", **kw)
    # Same input content -> identical panel content checksum (deterministic).
    assert (
        a.dataset_checksums["league_panel.parquet"] == b.dataset_checksums["league_panel.parquet"]
    )
