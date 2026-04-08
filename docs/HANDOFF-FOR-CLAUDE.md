# Handoff Notes: Superblock / Taktikos Research

**For:** Claude (incoming agent)
**From:** Fresh (Opus 4.6, OpenClaw)
**Date:** 2026-04-08
**Branch:** `research/taktikos`
**Repo:** github.com/ottobot-ai/dilf4s

---

## What This Project Is

You're picking up an active research paper:

> **"Superblock Proofs for Proof-of-Stake: How Local Dynamic Difficulty Enables NIPoPoW-Style Light Clients"**

The paper makes a structural argument: Ouroboros Taktikos's *Local Dynamic Difficulty* (LDD) — an obscure protocol modification originally proposed for stake-leakage resistance — accidentally creates a difficulty hierarchy that enables permissionless NIPoPoW-style superblock proofs in PoS. This is the **first** PoS construction that gives trustless light clients without coordination.

James (the human you're working with) is the lead author. He cares deeply about narrative coherence and structural correctness, not just numbers. He'll push back hard on hand-waving.

---

## The Core Thesis (Read This First)

The paper establishes a **separation theorem** between two distinct functions:

| Function | Governs | Layer |
|---|---|---|
| **Election function** | Settlement security (consistency, liveness) | Consensus layer |
| **Weight function** | Light-client proof size | NIPoPoW layer |

The key insight: **the LDD slot-gap gating creates an asymmetry that improves the consistency bound by ~20%** compared to a flat difficulty Praos baseline. But weighting blocks by their gap (the "ramp weight" idea) does NOT improve settlement security and actually hurts grinding resistance. Weighting is therefore relegated to the light-client proof layer only.

This separation is the paper's main contribution. Everything else supports it.

**Permissionless framing:** Every existing trustless light-client scheme for PoS requires committee coordination, validator selection, or bridges. Ours requires neither — it just uses the natural hierarchy that LDD already produces. That's the headline.

---

## Required Reading (in order)

### 1. The Paper Itself
- **`paper/main.tex`** — 663 lines, the actual LaTeX source
- **`paper/main.pdf`** — last compiled version (commit `03aa359`)

Read sections in this order:
1. Abstract + Introduction (sets up the permissionless light-client claim)
2. Section on LDD mechanics (the snowplow curve)
3. Separation theorem (the conceptual core)
4. Grinding resistance section (Fig 9 — the key empirical result)
5. Conclusion (recently rewritten — leads with the structural argument)

### 2. Background on Taktikos Itself
- **`docs/TAKTIKOS-NOTES.md`** — design notes covering the protocol
- **`docs/taktikos-fc2023.pdf`** — original Ouroboros Taktikos paper (FC 2023)

The snowplow curve from the original paper:
```
f(δ) = 0                              if δ < ψ       (dormant)
       fA × (δ - ψ) / (γ - ψ)        if ψ ≤ δ < γ   (ramp)
       fB                              if δ ≥ γ        (recovery/baseline)

threshold = 1 - (1 - f(δ))^α
```

Where ψ = offset, γ = cutoff, fA = amplitude, fB = baseline, α = relative stake.

### 3. Citation Database
- **`paper/REFERENCES-RESEARCH.md`** — annotated bibliography organized by topic, with MUST-CITE / SHOULD-CITE / OPTIONAL tiers. Each entry has a connection note explaining how it relates to our argument.

Key citations to know:
- Kiayias, Miller, Zindros (FC 2020) — original NIPoPoWs paper
- Bünz et al. (S&P 2020) — FlyClient
- Kiayias, Russell, David, Oliynykov — Ouroboros Praos (the foil)

### 4. Simulation Code & Results
- **`paper/analysis/RESULTS.md`** — narrative summary of simulation findings
- **`paper/analysis/`** — Python simulation scripts (see "Code Layout" below)
- **`paper/analysis/grinding_results_ci.json`** — current Fig 9 data with 95% CI

---

## Code Layout

### Scala Reference Implementation
- **`taktikos/src/main/scala/xyz/kd5ujc/taktikos/`**
  - `LeaderElection.scala` — VRF eligibility implementation
  - `TaktikosSimulation.scala` — Scala-side simulation (⚠️ has known bug, see "Known Issues")
  - `models.scala` — data types

The Scala code is the canonical reference for what the protocol actually does. Python sims should match its semantics.

### Python Analysis & Simulations
Located in `paper/analysis/`. The active files used in the current paper:

| File | Purpose | Status |
|---|---|---|
| `challengerModel_ramp.py` | Grinding sim, 3 schemes (Static / LDD plain / LDD+ramp) | Active — produces Fig 9 |
| `run_grinding_ci.py` | Multi-trial CI runner wrapping `challengerModel_ramp.py` | Active |
| `gating_asymmetry.py` | Computes the ~20% consistency bound improvement | Active — produces Fig 8 |
| `consistency_bound_*.py` | Various analytical bounds (final, hybrid, ramp, w3, w3_hardened) | Reference — `consistency_bound_final.py` is canonical |
| `fork_race_sim.py` | Fork race simulation | Active — produces Fig 4 |
| `l0_comparison.py` | Praos vs Taktikos threshold comparison | Active — produces Figs 10, 11 |
| `chain_weight.py` | Cumulative weight analysis | Active |
| `selfish_mining_sim.py` | Adversarial strategy sim | Used in earlier sections |
| `weight_grinding_intuition_v2.py` | Conceptual diagram for the grinding intuition | Active |

**⚠️ Cleanup needed:** Many `_v2`, `_v3`, `_v4` files are dead code from earlier iterations. Don't trust filenames — verify what's actually imported by the figure-generation scripts before editing.

### Figure Generation
- **`paper/figures/generate_paper_figures.py`** — main figure generator (uses `paper/data/`)
- **`paper/figures/generate_figures.py`** — older entry point, may be redundant
- **`paper/figures/fig_grinding_intuition_tikz.tex`** — hand-crafted TikZ diagram for the conceptual panel

---

## The 11 Figures

| # | What it shows | File |
|---|---|---|
| 1 | Threshold curves (snowplow) | matplotlib |
| 2 | Slot-gap gating mechanic | matplotlib |
| 3 | Stake-leakage dilemma | matplotlib |
| 4 | Suppression / fork race (500-race ensemble, median + 10/90 bands) | `fork_race_sim.py` |
| 5 | Block production density | matplotlib |
| 6 | Adversarial strategies | matplotlib |
| 7 | Cumulative weight comparison | `chain_weight.py` |
| 8 | Gating asymmetry (the ~20% improvement) | `gating_asymmetry.py` |
| 9 | **Grinding comparison (3 schemes, 95% CI bands)** | `challengerModel_ramp.py` + `run_grinding_ci.py` |
| 10 | Praos vs Taktikos L0 | `l0_comparison.py` |
| 11 | L0 curves (two-panel: raw thresholds, then squared α=2; Taktikos spans 47× weight range vs Praos flat) | `l0_comparison.py` |

**Fig 9 is the most important empirical figure.** It's the headline grinding resistance result.

---

## Current State of the Paper

### What's done
- Core thesis written and rewritten multiple times — current framing is the "permissionless light-client" angle (commit `e8e2087`)
- Separation theorem section
- All 11 figures generated and embedded
- Fig 9 has 95% CI bands from 20 trials
- Fig 4 has 500-race ensemble bands
- Conclusion recently rewritten to lead with the structural argument

### What's in progress / open
1. **Hand-crafted TikZ diagram** for panel (a) of the grinding intuition — James proposed showing honest chain (filled squares) + adversary diamonds with dormant gap, demonstrating weight 3.8 vs 6×w≈1 honest blocks. Stub exists at `paper/figures/fig_grinding_intuition_tikz.tex`.
2. **CIs on other simulation figures** — Fig 9 has them, others should too (settlement violation plots especially).
3. **Reproduction README** in `paper/analysis/` — currently no canonical "how to rerun the experiments" doc. Many scripts have hardcoded params; need to document.
4. **Narrative coherence pass** — make sure election vs weight separation is clear throughout, not just in the theorem section.
5. **Zenodo DOI + git tag** `v1.0-submission` (not yet done)
6. **Anomaly investigation:** In Fig 9, "LDD plain" appears worse than "Static PoS" at certain adversary stakes. Suspected to be a simulation artifact, not a real result. Needs verification.
7. **Open theoretical question:** Can the consistency bound smoothly vary to *match* PoW at all block-production frequencies, or is there a fundamental gap? James cares about this — it would strengthen the paper significantly if answered positively.

---

## Known Issues & Gotchas

### Bugs

1. **`taktikos/src/main/scala/xyz/kd5ujc/taktikos/TaktikosSimulation.scala`** calls `checkEligibilityAllLevels` with the wrong argument signature — missing `slotGap` and `baseBlockCount`. The Scala sim doesn't currently run end-to-end. Fix this if you need the Scala sim; otherwise the Python sims are the source of truth.

2. **Earlier iterations of the ramp weight computation** had a bug where the pure ramp score telescoped to `last_slot / MEAN_GAP`, making honest trivially always win. The fix lives in `challengerModel_ramp.py` which uses the challenger model internals correctly. **Don't reintroduce the telescoping shortcut.**

### Constants you'll see
- `MEAN_GAP = 5.2014` — stationary mean gap for r=1 from the Taktikos snowplow distribution. This is empirically derived and used throughout the ramp weight calculations.
- `k = 6` — common settlement parameter in earlier single-run experiments.

### Don't waste tokens on
- The `_v2`, `_v3`, `_v4` analysis files. They're earlier iterations. Verify what's actually imported by `generate_paper_figures.py` or `run_grinding_ci.py` before touching anything.
- Recompiling the paper just to verify — `pdflatex` works, `main.pdf` is the latest version. Only recompile if you've changed `main.tex` or a referenced figure.

---

## How to Work With James

He's particular about:
- **Narrative coherence over technical density.** The paper needs to *read* well, not just be correct. He'll rewrite paragraphs that feel hand-wavy.
- **The "obscure technique → permissionless rollup mechanism" framing.** Taktikos is not well-known. Part of the paper's job is to explain *why anyone should care* about this protocol. The pitch is: it's the missing piece for trustless PoS light clients.
- **Statistical rigor.** Single-run results aren't trusted; he wants CI bands or n>=20 trials.
- **Honesty about what's not proven.** Don't oversell. The grinding sim is empirical, not analytical — say so.

He's NOT particular about:
- Code style in throwaway analysis scripts
- LaTeX micro-formatting (within reason)

When uncertain, **ask** before making large changes to `main.tex`. Small fixes (typos, citation cleanup) are fine.

---

## Useful OpenClaw Skills (if you have them)

If you're running inside OpenClaw with skill access:
- **`graphviz-diagrams`** — for any flowchart-style diagrams (not relevant for the paper figures, which are matplotlib/TikZ)
- **`memory-management`** — read `~/.openclaw/workspace-fresh/MEMORY.md` for cross-project context if you want more background
- **`task-management`** — `TASKS.md` in the workspace tracks active work

If you're standalone Claude (no OpenClaw), ignore those.

---

## Suggested First Actions

1. `git status && git log --oneline -10 && git diff HEAD~5 -- paper/main.tex` — see what's changed recently
2. Open `paper/main.pdf` and read the abstract + intro + conclusion
3. Read `docs/TAKTIKOS-NOTES.md` for protocol fundamentals
4. Skim `paper/REFERENCES-RESEARCH.md` to understand the citation landscape
5. Run `cd paper/analysis && python challengerModel_ramp.py` (should produce a plot in a few seconds)
6. **Then ask James what he wants you to focus on.** Don't dive into changes without alignment.

---

## Repository Conventions

- Python: no formal style enforcement, but match existing patterns. `numpy`, `matplotlib`, no heavy frameworks.
- Scala: scalafmt config in repo root.
- LaTeX: keep figures referenced by `\label` and use `\ref`. Bibliography is in-line `\bibitem` style for now (no separate `.bib` yet).
- Git: feature branches off `research/taktikos`. Don't push directly to main of dilf4s — it's still tracking the original codebase.

---

## Quick Links

- **Branch:** `research/taktikos`
- **Latest PDF:** `paper/main.pdf` (commit `03aa359`)
- **Active simulations:** `paper/analysis/challengerModel_ramp.py`, `run_grinding_ci.py`
- **Key figure data:** `paper/analysis/grinding_results_ci.json`
- **Conceptual notes:** `docs/TAKTIKOS-NOTES.md`
- **Citations:** `paper/REFERENCES-RESEARCH.md`
- **Original Taktikos paper:** `docs/taktikos-fc2023.pdf`

---

Good luck. The paper is in a strong place — most of the heavy lifting is done. Your job is probably polish, the open theoretical question, and the cleanup items in "What's in progress." Don't break Fig 9.

— Fresh 🧪
