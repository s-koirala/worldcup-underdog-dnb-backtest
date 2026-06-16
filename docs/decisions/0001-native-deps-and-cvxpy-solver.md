---
name: ADR-0001 — Native/system dependencies and the cvxpy solver backend
description: Enumerate the BLAS/LAPACK backend and pin the cvxpy convex solver (Clarabel) so the vector-Kelly program is reproducible on a clean machine
type: dependency
status: accepted
date: 2026-06-16
supersedes:
superseded_by: ""
---

# ADR-0001 — Native/system dependencies and the cvxpy solver backend

## Context

Reproducibility-from-source is the dominant project risk: declared dependencies expand ~13.5× to
the runtime closure and only 68.3% of LLM-generated projects run out-of-the-box
([arXiv 2512.22387](https://arxiv.org/abs/2512.22387), *AI-Generated Code Is Not Reproducible
(Yet)*). The `==`-pinned manifest ([pyproject.toml](../../pyproject.toml)) and the committed
`uv.lock` ([uv.lock](../../uv.lock)) fix the **Python** closure, but several dependencies link
**native** code whose backend is not captured by a PyPI version string alone:

- `numpy` / `scipy` link a **BLAS/LAPACK** backend; the linear-algebra backend changes numeric
  results at the ULP level and the available build (OpenBLAS vs MKL vs Accelerate) is
  platform-dependent.
- `cvxpy` (the Phase-3 concurrent-matchday **vector-Kelly** program, `max_f Σ_k π_k log((Of)_k)`
  s.t. `1ᵀf=1, f≥0` — STAKE §5.2) dispatches to a **solver backend** that is a separate native
  package; an unpinned solver makes the optimum (and therefore the deployed stake vector)
  non-reproducible across machines, and some solvers ship no wheel for the target platform.

This ADR enumerates the native/system dependencies and **names the chosen cvxpy solver with its
install path** so the convex program is reproducible on a clean machine (plan task 1c; §D.8).

## Decision

### BLAS / LAPACK backend

Adopt the **OpenBLAS backend bundled inside the official numpy/scipy PyPI wheels**
(`scipy-openblas`), i.e. no system-level BLAS is required or used. Realized backend on the pinned
environment (probed 2026-06-16 via `numpy.show_config`):

- `numpy==2.2.6` → BLAS/LAPACK = **`scipy-openblas` 0.3.29**
- `scipy==1.15.3` → BLAS/LAPACK = **`scipy-openblas` 0.3.29**

No MKL, no system OpenBLAS, no Accelerate. The bundled OpenBLAS travels inside the wheel, so
`uv sync --frozen` reproduces the exact linear-algebra backend with **no system package manager
step** on any of the targeted platforms (the cp311 win_amd64 / manylinux / macOS wheels all carry
it). Do not install a system BLAS or an MKL-linked numpy build; that would silently change the
backend off the pinned `scipy-openblas` and break ULP-level numeric determinism.

### cvxpy solver backend

Pin **Clarabel** (`clarabel`, an interior-point conic solver) as the cvxpy solver for the
vector-Kelly program.

- **Install path:** Clarabel ships as a pure-wheel native package (`clarabel`, Rust core with a
  cp311 win_amd64 wheel) and is a hard, **bundled dependency of cvxpy ≥ 1.5** — it is pulled in by
  `cvxpy==1.6.6` with no extra step and is `uv.lock`-pinned (realized: `clarabel==0.11.1`). No C
  toolchain, no system solver, no separate `pip install` is required.
- **Why Clarabel:** the vector-Kelly objective is the sum of `log` terms, so the program is an
  **exponential-cone** problem. Clarabel natively supports the exponential cone, is cvxpy's
  **auto-selected default** for this problem family on the pinned environment (verified
  2026-06-16: the program auto-dispatches to `CLARABEL` and returns `optimal`), and is fully
  open-source with a wheel for every targeted platform. Pinning the auto-selected default makes the
  realized solve deterministic and identical to the no-`solver=` call.
- **Realized installed solvers** on the pinned environment (`cvxpy.installed_solvers()`,
  2026-06-16): `CLARABEL`, `OSQP`, `SCIPY`, `SCS`. `clarabel==0.11.1`, `scs==3.2.11`,
  `osqp==1.1.3`, all `uv.lock`-pinned.

The Phase-3 vector-Kelly call passes `solver=cvxpy.CLARABEL` **explicitly** (rather than relying on
the auto-default) so the choice is pinned in code and cannot drift if a future cvxpy changes its
default ordering.

### Registered fallbacks (not the default)

- **SCS** (`scs==3.2.11`, installed): a first-order conic solver that also supports the exponential
  cone. Registered as the **primary fallback** if a Clarabel solve fails to converge on a degenerate
  matchday slate; an SCS fallback must be logged in the run's ReproLog (`model_hash` / run record)
  so a non-default solve is never silent.
- **ECOS** is **not installed** and is **not adopted**: it is in maintenance-only status and cvxpy
  has moved its default exponential-cone path to Clarabel. Do not add ECOS as a dependency.
- **OSQP** (installed) is **QP-only** and cannot take the `log` objective; it is not a candidate for
  the vector-Kelly program and is present only as a cvxpy transitive dependency.

## Consequences

- **Positive.** The native surface (BLAS + conic solver) is fully captured by `uv.lock` with no
  system-package step, so `uv sync --frozen` reproduces the vector-Kelly optimum on a clean runner;
  the solver is the open-source auto-default, pinned explicitly in code.
- **New obligations.** Phase 3 passes `solver=cvxpy.CLARABEL` explicitly and logs any SCS fallback;
  CI must run on the same `scipy-openblas` wheels (do not substitute an MKL numpy in CI, or the
  platform-invariance acceptance check would fail on ULP drift).
- **Negative.** OpenBLAS is not the fastest backend (MKL can be faster on Intel); throughput is
  traded for backend reproducibility. The Monte-Carlo / bootstrap engines are the throughput
  bottleneck, not BLAS, so this is acceptable.

## Alternatives considered

- **MKL-linked numpy (e.g. conda `numpy` with `libblas=*=*mkl`).** Rejected: not the wheel default,
  pulls a large platform-specific native dependency outside `uv.lock`, and changes numeric results
  off the pinned `scipy-openblas` backend.
- **ECOS as the cvxpy solver.** Rejected: maintenance-only; cvxpy's default exponential-cone path is
  now Clarabel, which is bundled and wheel-available on every target.
- **SCS as the default.** Rejected as the *default* (kept as fallback): SCS is a first-order method
  with looser default tolerances than Clarabel's interior-point solve; Clarabel is the
  higher-accuracy auto-default for this program family.
- **OSQP.** Rejected: QP-only, cannot represent the `log`-utility exponential-cone objective.

## References

- [plan_phased-workplan_2026-06-16.md](../protocol/plan_phased-workplan_2026-06-16.md) Phase 0 task 1c (this ADR), task 1a/1b (interpreter band + `==`-pins), §D.8 (dependency pinning).
- [research_staking-bankroll_2026-06-16.md](../research/research_staking-bankroll_2026-06-16.md) §5.2 (convex vector-Kelly program `max_f Σ_k π_k log((Of)_k)`).
- [research_backtest-architecture-deliverables_2026-06-16.md](../research/research_backtest-architecture-deliverables_2026-06-16.md) §3.4 (tooling; `arch`/cvxpy/statsmodels).
- [arXiv 2512.22387](https://arxiv.org/abs/2512.22387) — *AI-Generated Code Is Not Reproducible (Yet)* (unpinned transitive surface as the dominant repro risk).
- [pyproject.toml](../../pyproject.toml) (`==`-pinned manifest), [uv.lock](../../uv.lock) (resolved transitive graph).
- Clarabel solver: [clarabel.org](https://clarabel.org/) (interior-point conic solver, exponential-cone support).
