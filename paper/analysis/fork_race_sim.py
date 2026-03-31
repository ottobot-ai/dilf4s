"""
fork_race_sim.py — Empirical fork race comparison of three PoS schemes.

Demonstrates that the "pure ramp" superblock weighting scheme (Scheme C) achieves
a better consistency bound than plain Taktikos LDD (Scheme B) and static PoS (Scheme A).

Analytical result (Taktikos paper): w(g) = g/mean achieves exactly the PoW
consistency bound for single-party block production under the snowplow LDD.
This simulation empirically validates that ordering via w(g) = g/mean_gap
improves fork resolution beyond plain block count.

Reference LDD model: ~/repos/consensus_automata/papers/taktikos/relative_forging_power.py
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from pathlib import Path

# ── Reproducibility ────────────────────────────────────────────────────────────
RNG = np.random.default_rng(42)

# ── Protocol parameters (Taktikos snowplow) ────────────────────────────────────
GAMMA = 15     # forging window (ramp cutoff)
FA    = 0.5    # snowplow amplitude
FB    = 0.05   # baseline difficulty (plateau)
PSI   = 0      # dormant period for L0

# ── Simulation parameters ──────────────────────────────────────────────────────
N_RACES  = 2000   # independent races per (scheme, beta)
RACE_LEN = 100    # race ends when honest party reaches this many blocks
N_SLOTS  = 8000   # slot budget per race (safety margin)

# ── Beta sweep ─────────────────────────────────────────────────────────────────
BETA_MIN, BETA_MAX, BETA_STEP = 0.05, 0.50, 0.01
BETAS = np.round(np.arange(BETA_MIN, BETA_MAX + BETA_STEP / 2, BETA_STEP), 4)

# ── Output dirs ────────────────────────────────────────────────────────────────
FIGURES_DIR = Path(__file__).parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# LDD difficulty functions
# ══════════════════════════════════════════════════════════════════════════════

def f_static(gap: int) -> float:
    """Scheme A: constant baseline — no LDD."""
    return FB


def f_snowplow(gap: int) -> float:
    """Scheme B/C: snowplow ramp then plateau."""
    if gap <= 0:
        return 0.0
    elif gap <= GAMMA:
        return FA * gap / GAMMA
    else:
        return FB


# ── Precompute stationary mean gap for Taktikos LDD (r=1 reference) ───────────
#
# Under f_snowplow with full stake r=1, the stationary distribution is:
#   pi[g] ∝ Π_{i=1}^{g-1} (1 - f_snowplow(i))
# Mean gap = Σ g · pi[g]
# Used to fix the normalization constant for the ramp weight w(g) = g / mean_gap.
# This is a protocol constant, independent of individual stake fractions.

def _compute_mean_gap(stake: float = 1.0) -> float:
    max_g = 5000
    acc = 1.0
    pi_raw = []
    for g in range(1, max_g + 1):
        pi_raw.append(acc)
        acc *= (1.0 - f_snowplow(g)) ** stake
        if acc < 1e-14:
            break
    pi_arr = np.array(pi_raw)
    pi_arr /= pi_arr.sum()
    g_axis = np.arange(1, len(pi_arr) + 1)
    return float((g_axis * pi_arr).sum())

# Network mean gap (r=1 reference, used as protocol constant for ramp weight)
MEAN_GAP = _compute_mean_gap(stake=1.0)
print(f"Snowplow LDD mean gap (r=1): {MEAN_GAP:.4f} slots")


# ══════════════════════════════════════════════════════════════════════════════
# Eligibility and scoring per scheme
# ══════════════════════════════════════════════════════════════════════════════

def eligible(gap: int, stake: float, scheme: str, rng: np.random.Generator) -> bool:
    """
    Returns True if the party produces a block at this gap.
    Staking test: block produced with probability 1 - (1 - f(gap))^stake.
    """
    if gap <= 0:
        return False
    if scheme == 'A':
        f = f_static(gap)
    else:  # 'B' or 'C'
        f = f_snowplow(gap)
    # Bernoulli draw with probability 1 - (1-f)^stake
    threshold = 1.0 - (1.0 - f) ** stake
    return rng.random() < threshold


def block_score(gap: int, scheme: str) -> float:
    """
    Score contribution of one block at gap `gap`.
    A/B: +1 (plain block count)
    C:   +g/mean_gap (pure ramp weight — analytically optimal)
    """
    if scheme in ('A', 'B'):
        return 1.0
    else:  # 'C'
        return gap / MEAN_GAP


def adv_target_gap(scheme: str, stake: float) -> int:
    """
    Adversary delay strategy: choose gap that maximises weight/time-ratio.

    For ramp w(g)=g/M: ratio w(g)/g = 1/M is flat for all g.
    So the adversary's optimal gap is MEAN_GAP (not worth waiting longer).
    For static PoS / plain count: produce as soon as eligible (gap=1).
    """
    if scheme == 'C':
        # Flat w(g)/g ratio: picking gap=mean_gap is weakly optimal
        # (any gap in [1, mean_gap] is equivalent; we use mean)
        return max(1, round(MEAN_GAP))
    else:
        # No weight advantage: produce at gap=1 (first eligible)
        return 1


# ══════════════════════════════════════════════════════════════════════════════
# Single race simulation
# ══════════════════════════════════════════════════════════════════════════════

def run_race(beta: float, scheme: str, rng: np.random.Generator) -> bool:
    """
    Simulate one fork race.

    Honest party (stake 1-beta): produce at every eligible slot immediately.
    Adversary  (stake beta):     delay strategy — wait until target_gap before drawing.

    Returns True if adversary wins (adv_score >= honest_score when race ends).
    """
    honest_stake = 1.0 - beta
    adv_stake    = beta

    honest_blocks    = 0
    honest_score     = 0.0
    adv_score        = 0.0
    honest_last_slot = 0
    adv_last_slot    = 0

    target = adv_target_gap(scheme, adv_stake)

    for slot in range(1, N_SLOTS + 1):
        # — Honest party: produce at first eligible slot —
        honest_gap = slot - honest_last_slot
        if eligible(honest_gap, honest_stake, scheme, rng):
            honest_blocks += 1
            honest_score  += block_score(honest_gap, scheme)
            honest_last_slot = slot
            if honest_blocks >= RACE_LEN:
                break

        # — Adversary: only attempt at/after target gap —
        adv_gap = slot - adv_last_slot
        if adv_gap >= target and eligible(adv_gap, adv_stake, scheme, rng):
            adv_score    += block_score(adv_gap, scheme)
            adv_last_slot = slot

    return adv_score >= honest_score


# ══════════════════════════════════════════════════════════════════════════════
# Main sweep
# ══════════════════════════════════════════════════════════════════════════════

def sweep_scheme(scheme: str) -> np.ndarray:
    """Run N_RACES races for every beta; return array of adversary win rates."""
    win_rates = []
    for beta in BETAS:
        wins = sum(run_race(beta, scheme, RNG) for _ in range(N_RACES))
        win_rates.append(wins / N_RACES)
    return np.array(win_rates)


# ══════════════════════════════════════════════════════════════════════════════
# Consistency bound: interpolated beta where win_rate first crosses 0.5
# ══════════════════════════════════════════════════════════════════════════════

def consistency_bound(win_rates: np.ndarray) -> float:
    """
    Return the beta threshold (interpolated) where adversary win rate crosses 0.5.
    If never crosses, return BETA_MAX.
    """
    for i in range(len(win_rates) - 1):
        if win_rates[i] < 0.5 <= win_rates[i + 1]:
            # Linear interpolation
            b1, b2 = BETAS[i], BETAS[i + 1]
            w1, w2 = win_rates[i], win_rates[i + 1]
            if w2 != w1:
                return b1 + (0.5 - w1) * (b2 - b1) / (w2 - w1)
            return b1
    return float(BETA_MAX)


# ══════════════════════════════════════════════════════════════════════════════
# Run all three schemes
# ══════════════════════════════════════════════════════════════════════════════

print(f"\nRunning {N_RACES} races × {len(BETAS)} beta values × 3 schemes …")
print(f"Beta range: [{BETAS[0]:.2f}, {BETAS[-1]:.2f}] in steps of {BETA_STEP}")

print("  Scheme A (Static PoS)…", flush=True)
wr_A = sweep_scheme('A')

print("  Scheme B (Taktikos LDD, plain count)…", flush=True)
wr_B = sweep_scheme('B')

print("  Scheme C (Taktikos LDD + ramp weight)…", flush=True)
wr_C = sweep_scheme('C')

cb_A = consistency_bound(wr_A)
cb_B = consistency_bound(wr_B)
cb_C = consistency_bound(wr_C)

print("\n=== FORK RACE SIMULATION RESULTS ===")
print(f"Scheme A (Static PoS):          beta < {cb_A:.3f}  (adversary wins >50% at beta={cb_A:.3f})")
print(f"Scheme B (Taktikos, no weight): beta < {cb_B:.3f}")
print(f"Scheme C (Taktikos + ramp):     beta < {cb_C:.3f}")
print(f"PoW reference:                  beta < 0.500")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 1: Win rate vs adversarial stake
# ══════════════════════════════════════════════════════════════════════════════

fig1, ax1 = plt.subplots(figsize=(8, 5))

ax1.plot(BETAS, wr_A, 'r-o',  markersize=3, label='A: Static PoS (plain count)')
ax1.plot(BETAS, wr_B, 'b-s',  markersize=3, label='B: Taktikos LDD (plain count)')
ax1.plot(BETAS, wr_C, 'g-^',  markersize=3, label='C: Taktikos LDD + ramp weight')

# Mark 50% crossing
ax1.axhline(0.5, color='k', linestyle='--', linewidth=0.8, label='50% line')
for cb, wr, color, label in [(cb_A, wr_A, 'r', 'A'), (cb_B, wr_B, 'b', 'B'), (cb_C, wr_C, 'g', 'C')]:
    ax1.axvline(cb, color=color, linestyle=':', linewidth=0.9, alpha=0.7)
    ax1.annotate(f'{label}: β*={cb:.3f}',
                 xy=(cb, 0.5), xytext=(cb + 0.005, 0.5 + 0.03 * (1 if label == 'C' else -1 if label == 'B' else 0)),
                 fontsize=8, color=color)

ax1.set_xlabel('Adversarial stake β')
ax1.set_ylabel('Adversary win rate')
ax1.set_title(f'Fork race win rate vs adversarial stake\n'
              f'(N={N_RACES} races, {RACE_LEN}-block race, delay adversary)')
ax1.legend(loc='upper left', fontsize=9)
ax1.set_xlim(BETAS[0], BETAS[-1])
ax1.set_ylim(-0.02, 1.02)
ax1.grid(True, alpha=0.3)

fig1.tight_layout()
fig1.savefig(FIGURES_DIR / 'fork_race_win_rate.png', dpi=150)
print(f"\nSaved: {FIGURES_DIR / 'fork_race_win_rate.png'}")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 2: Consistency bound comparison bar chart
# ══════════════════════════════════════════════════════════════════════════════

fig2, ax2 = plt.subplots(figsize=(7, 5))

schemes     = ['A\nStatic PoS', 'B\nTaktikos\n(plain count)', 'C\nTaktikos\n+ ramp weight']
bounds      = [cb_A, cb_B, cb_C]
colors      = ['#d62728', '#1f77b4', '#2ca02c']
bars        = ax2.bar(schemes, bounds, color=colors, width=0.4, edgecolor='black', linewidth=0.8)

# PoW reference line
ax2.axhline(0.500, color='k', linestyle='--', linewidth=1.5, label='PoW reference (β=0.500)')

# Annotate bars
for bar, b in zip(bars, bounds):
    ax2.text(bar.get_x() + bar.get_width() / 2, b + 0.003,
             f'β* = {b:.3f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

ax2.set_ylim(0, 0.57)
ax2.set_ylabel('Consistency bound β*\n(adversary wins <50% of races for β < β*)')
ax2.set_title(f'Consistency bound comparison\n'
              f'(N={N_RACES} races per beta, delay adversary, {RACE_LEN}-block race)')
ax2.legend(loc='upper left')
ax2.grid(True, axis='y', alpha=0.3)

fig2.tight_layout()
fig2.savefig(FIGURES_DIR / 'consistency_bound_comparison_sim.png', dpi=150)
print(f"Saved: {FIGURES_DIR / 'consistency_bound_comparison_sim.png'}")

# ══════════════════════════════════════════════════════════════════════════════
# Figure 3: Safety margin (honest/adv score ratio) vs beta
# ══════════════════════════════════════════════════════════════════════════════

def safety_margin_sweep(scheme: str) -> np.ndarray:
    """Return honest_score / adv_score averaged over N_RACES for each beta."""
    margins = []
    for beta in BETAS:
        ratios = []
        for _ in range(N_RACES):
            honest_stake = 1.0 - beta
            adv_stake    = beta
            honest_blocks    = 0
            honest_score     = 0.0
            adv_score_inner  = 0.0
            honest_last_slot = 0
            adv_last_slot    = 0
            target           = adv_target_gap(scheme, adv_stake)
            for slot in range(1, N_SLOTS + 1):
                honest_gap = slot - honest_last_slot
                if eligible(honest_gap, honest_stake, scheme, RNG):
                    honest_blocks += 1
                    honest_score  += block_score(honest_gap, scheme)
                    honest_last_slot = slot
                    if honest_blocks >= RACE_LEN:
                        break
                adv_gap = slot - adv_last_slot
                if adv_gap >= target and eligible(adv_gap, adv_stake, scheme, RNG):
                    adv_score_inner += block_score(adv_gap, scheme)
                    adv_last_slot    = slot
            if adv_score_inner > 0:
                ratios.append(honest_score / adv_score_inner)
            else:
                ratios.append(float(honest_score if honest_score > 0 else 1.0))
        margins.append(np.mean(ratios))
    return np.array(margins)

print("  Computing safety margins for Figure 3…", flush=True)
sm_A = safety_margin_sweep('A')
sm_B = safety_margin_sweep('B')
sm_C = safety_margin_sweep('C')

fig3, ax3 = plt.subplots(figsize=(8, 5))
ax3.plot(BETAS, sm_A, 'r-o', markersize=3, label='A: Static PoS')
ax3.plot(BETAS, sm_B, 'b-s', markersize=3, label='B: Taktikos LDD (plain count)')
ax3.plot(BETAS, sm_C, 'g-^', markersize=3, label='C: Taktikos LDD + ramp weight')
ax3.axhline(1.0, color='k', linestyle='--', linewidth=0.8, label='Parity (honest=adv)')
ax3.set_xlabel('Adversarial stake β')
ax3.set_ylabel('Average honest/adversary score ratio')
ax3.set_title('Safety margin: honest score ÷ adversary score\n(higher = more honest advantage)')
ax3.legend(loc='upper right', fontsize=9)
ax3.set_xlim(BETAS[0], BETAS[-1])
ax3.grid(True, alpha=0.3)
fig3.tight_layout()
fig3.savefig(FIGURES_DIR / 'fork_race_safety_margin.png', dpi=150)
print(f"Saved: {FIGURES_DIR / 'fork_race_safety_margin.png'}")

plt.close('all')
print("\nDone.")
