# Per-phase reproducibility targets (plan task 9; §D.7).
#
# Each stage target invokes the per-phase entrypoint (src.run) so a reviewer can
# regenerate one phase in isolation; each emits its own ReproLog (one per stage,
# its own run_id) and has its own --dry-run acceptance check mirroring the
# Phase-0 criterion. `make reproduce` runs the full chain.
#
# Cross-platform: uses `uv run` (no shell-specific syntax) so the same targets
# run on the Windows authoring host and the ubuntu/windows CI matrix.

CONFIG ?= config/baseline.yaml
UV     ?= uv

.PHONY: help sync lint test check \
        reproduce reproduce-wc reproduce-data reproduce-validate reproduce-pricing \
        reproduce-staking reproduce-inference reproduce-deliver \
        dry-run-data dry-run-validate dry-run-pricing dry-run-staking \
        dry-run-inference dry-run-deliver dry-run-all

help:
	@echo "Targets:"
	@echo "  sync                 uv sync --frozen (prove out-of-the-box install)"
	@echo "  lint                 ruff check + format --check"
	@echo "  test                 pytest"
	@echo "  check                lint + test (CI gate)"
	@echo "  dry-run-all          Phase-0 --dry-run for every stage"
	@echo "  reproduce            full per-phase chain"
	@echo "  reproduce-wc         build the World-Cup hold-out panel (RESULTS sources)"
	@echo "  reproduce-data       ingest stage (depends on reproduce-wc)"
	@echo "  reproduce-validate   validate stage"
	@echo "  reproduce-pricing    price stage"
	@echo "  reproduce-staking    stake stage"
	@echo "  reproduce-inference  infer stage"
	@echo "  reproduce-deliver    report stage"

# --- Environment + quality gates --------------------------------------------
sync:
	$(UV) sync --frozen

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

test:
	$(UV) run pytest

check: lint test

# --- Per-phase Phase-0 dry-runs (acceptance check per stage) ----------------
dry-run-data:
	$(UV) run python -m src.run --config $(CONFIG) --stage ingest --dry-run
dry-run-validate:
	$(UV) run python -m src.run --config $(CONFIG) --stage validate --dry-run
dry-run-pricing:
	$(UV) run python -m src.run --config $(CONFIG) --stage price --dry-run
dry-run-staking:
	$(UV) run python -m src.run --config $(CONFIG) --stage stake --dry-run
dry-run-inference:
	$(UV) run python -m src.run --config $(CONFIG) --stage infer --dry-run
dry-run-deliver:
	$(UV) run python -m src.run --config $(CONFIG) --stage report --dry-run

dry-run-all: dry-run-data dry-run-validate dry-run-pricing \
             dry-run-staking dry-run-inference dry-run-deliver

# --- Per-phase compute -------------------------------------------------------
# Phase 1 implements the real `ingest` (league download + canonical-panel
# assembly) and `validate` (DATA §8 gates + draw-rate base rates) compute, each
# emitting its own ReproLog. The remaining stages (price/stake/infer/report) land
# in later phases and, until then, run their --dry-run acceptance check.
#
# The canonical data/processed/matches.parquet binds the World-Cup settlement
# block, whose RESULTS inputs (jfjelstul/martj42) are NOT downloaded by the league
# ingest. `reproduce-wc` rebuilds the WC hold-out panel from those pinned snapshots
# (reproducible-from-snapshot; plan task 4) BEFORE ingest assembles + checksums the
# canonical panel; ingest fails closed if the WC panel is absent. This binds the WC
# inputs into the documented `make reproduce` chain (major Phase-1 finding fix).
reproduce-wc:
	$(UV) run python -m src.build_wc_panel

reproduce-data: reproduce-wc
	$(UV) run python -m src.run --config $(CONFIG) --stage ingest
reproduce-validate:
	$(UV) run python -m src.run --config $(CONFIG) --stage validate
reproduce-pricing: dry-run-pricing
reproduce-staking: dry-run-staking
reproduce-inference: dry-run-inference
reproduce-deliver: dry-run-deliver

reproduce: reproduce-data reproduce-validate reproduce-pricing \
           reproduce-staking reproduce-inference reproduce-deliver
