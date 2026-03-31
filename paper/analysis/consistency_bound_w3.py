#!/usr/bin/env python3
"""
W3 Plateau Weight Function — Consistency Bound Analysis

Analyzes the W3 weight function (plateau at mode, Gaussian taper outside)
vs the current weight function w(B) = f(δ)^α for NiPoPoW-style superblock
proofs on Taktikos PoS (LDD-based).

Key question: Does W3 remove the adversarial incentive to delay (voluntarily
extend slot gaps to get heavier blocks)?
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from math import exp, log, sqrt
import os

# ─── Parameters ───────────────────────────────────────────────────────────────
LEVELS = {
    1: (0.990000, 0.1000),
    2: (0.511239, 1.9973),
    3: (0.215899, 4.0007),
    4: (0.111954, 8.0001),
    5: (0.047830, 16.000),
}
PSI = 1
AMPLITUDE, BASELINE, CUTOFF = 0.5, 0.05, 15
ALPHA = 2
R_NATURAL = 0.14  # natural fill rate

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

# ─── Core functions ───────────────────────────────────────────────────────────

def snowplow(slot_gap):
    """LDD snowplow threshold."""
    if slot_gap <= 0:
        return 0.0
    if slot_gap < CUTOFF:
        diff = AMPLITUDE * slot_gap / CUTOFF
    else:
        diff = BASELINE
    return min(diff, 1.0)

def shifted_exp_thr(gap, mp, sc):
    """Shifted exponential threshold for level L."""
    if gap < PSI:
        return 0.0
    return min(1.0, mp * (1.0 - exp(-(gap - PSI) / sc)))

def w_current(slot_gap):
    """Current weight: amplified LDD threshold."""
    f = snowplow(slot_gap)
    return f ** ALPHA

def w3(gap, mode, mean, sigma_left_factor=0.5):
    """
    W3 plateau weight function.
    Peak at mode, flat plateau [mode, mean], Gaussian taper outside.
    """
    sigma_left = mode * sigma_left_factor
    sigma_right = mean * 0.5
    if gap < mode:
        if sigma_left == 0:
            return 0.0
        return exp(-0.5 * ((gap - mode) / sigma_left) ** 2)
    elif gap <= mean:
        return 1.0
    else:
        return exp(-0.5 * ((gap - mean) / sigma_right) ** 2)

# ─── Gap distribution (renewal theory) ───────────────────────────────────────

def gap_pmf(mp, sc, max_gap=500):
    """
    Stationary gap distribution under shifted exponential election threshold.
    P(gap = g) ∝ P(elected at g) * P(not elected at 1..g-1)
    Renewal theory: probability of gap = g is proportional to the hazard rate.
    """
    # P(block at gap g) = shifted_exp_thr(g, mp, sc) * product_{k=1}^{g-1} (1 - shifted_exp_thr(k, mp, sc))
    pmf = np.zeros(max_gap + 1)
    survival = 1.0
    for g in range(1, max_gap + 1):
        h = shifted_exp_thr(g, mp, sc)
        pmf[g] = h * survival
        survival *= (1.0 - h)
        if survival < 1e-12:
            break
    total = pmf.sum()
    if total > 0:
        pmf /= total
    return pmf

def gap_mode_mean(pmf):
    """Compute mode and mean of gap distribution."""
    gaps = np.arange(len(pmf))
    mode = int(np.argmax(pmf))
    mean = float(np.dot(gaps, pmf))
    return mode, mean

def expected_weight(w_fn, pmf):
    """E[w | honest] using gap pmf."""
    total = 0.0
    for g in range(len(pmf)):
        if pmf[g] > 0:
            total += w_fn(g) * pmf[g]
    return total

# ─── Analysis 1: Parameter sweep ─────────────────────────────────────────────

def analysis_param_sweep():
    print("\n=== Analysis 1: W3 Parameter Sweep ===")
    sigma_factors = [0.1, 0.25, 0.5, 0.75, 1.0]
    n_levels = len(LEVELS)
    n_sigma = len(sigma_factors)

    fig, axes = plt.subplots(n_levels, 1, figsize=(12, 4 * n_levels))
    if n_levels == 1:
        axes = [axes]

    results = {}
    for idx, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ax = axes[idx]

        best_ratios = []
        e_honest_list = []
        e_burst_list = []
        e_delay_list = []

        for sf in sigma_factors:
            def wfn(g, sf=sf):
                return w3(g, mode, mean, sf)

            e_honest = expected_weight(wfn, pmf)

            # Burst: uniform over [1, mode-1]
            burst_gaps = list(range(1, max(2, mode)))
            e_burst = np.mean([wfn(g) for g in burst_gaps]) if burst_gaps else 0.0

            # Delay: uniform over [mean*2, mean*3]
            delay_lo = int(mean * 2)
            delay_hi = int(mean * 3) + 1
            delay_gaps = list(range(delay_lo, delay_hi + 1))
            e_delay = np.mean([wfn(g) for g in delay_gaps]) if delay_gaps else 0.0

            denom = max(e_burst, e_delay)
            best_ratio = e_honest / denom if denom > 0 else float('inf')

            best_ratios.append(best_ratio)
            e_honest_list.append(e_honest)
            e_burst_list.append(e_burst)
            e_delay_list.append(e_delay)

        results[level] = {
            'mode': mode, 'mean': mean,
            'best_ratios': best_ratios,
            'e_honest': e_honest_list,
            'e_burst': e_burst_list,
            'e_delay': e_delay_list,
        }

        x = np.arange(n_sigma)
        width = 0.2
        ax.bar(x - width, e_honest_list, width, label='E[w|honest]', color='steelblue', alpha=0.8)
        ax.bar(x, e_burst_list, width, label='E[w|burst]', color='tomato', alpha=0.8)
        ax.bar(x + width, e_delay_list, width, label='E[w|delay]', color='orange', alpha=0.8)

        ax2 = ax.twinx()
        ax2.plot(x, best_ratios, 'g^--', linewidth=2, markersize=8, label='best_ratio')
        ax2.axhline(1.0, color='gray', linestyle=':', linewidth=1)
        ax2.set_ylabel('honest/max(burst,delay)', color='green')
        ax2.tick_params(axis='y', labelcolor='green')

        ax.set_title(f'Level {level}: mode={mode}, mean={mean:.1f}  (mp={mp}, sc={sc})')
        ax.set_xlabel('sigma_left_factor')
        ax.set_ylabel('Expected weight')
        ax.set_xticks(x)
        ax.set_xticklabels([str(s) for s in sigma_factors])
        ax.legend(loc='upper left')
        ax2.legend(loc='upper right')

        # Print summary
        best_idx = np.argmax(best_ratios)
        print(f"  Level {level}: mode={mode}, mean={mean:.1f}")
        for i, sf in enumerate(sigma_factors):
            print(f"    σ_L={sf}: E[honest]={e_honest_list[i]:.4f}, "
                  f"E[burst]={e_burst_list[i]:.4f}, E[delay]={e_delay_list[i]:.4f}, "
                  f"ratio={best_ratios[i]:.3f}")
        print(f"    Best σ_L={sigma_factors[best_idx]} (ratio={best_ratios[best_idx]:.3f})")

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "consistency_w3_param_sweep.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")
    return results

# ─── Analysis 2: Consistency bound curves ────────────────────────────────────

def max_weight_per_slot(w_fn, max_gap=500):
    """
    Adversary optimal: find g* = argmax w(g)/g.
    Returns (g*, max w(g)/g).
    """
    best_val = 0.0
    best_g = 1
    for g in range(1, max_gap + 1):
        val = w_fn(g) / g
        if val > best_val:
            best_val = val
            best_g = g
    return best_g, best_val

def analysis_consistency_bounds():
    print("\n=== Analysis 2: Consistency Bound Curves ===")

    # Use level 3 as representative (mid-range)
    level = 3
    mp, sc = LEVELS[level]
    pmf = gap_pmf(mp, sc)
    mode, mean = gap_mode_mean(pmf)

    # Weight functions to compare
    schemes = {}
    schemes['Current (w=f^α)'] = {
        'fn': w_current,
        'color': 'tomato',
        'linestyle': '-',
    }
    schemes['W3 (σ=0.5)'] = {
        'fn': lambda g: w3(g, mode, mean, 0.5),
        'color': 'steelblue',
        'linestyle': '-',
    }
    schemes['W3 (σ=0.25)'] = {
        'fn': lambda g: w3(g, mode, mean, 0.25),
        'color': 'royalblue',
        'linestyle': '--',
    }
    # PoW reference: weight = 1 for all gaps
    schemes['PoW reference'] = {
        'fn': lambda g: 1.0,
        'color': 'green',
        'linestyle': ':',
    }

    betas = np.linspace(0.05, 0.48, 60)
    r = R_NATURAL

    fig, ax = plt.subplots(figsize=(10, 6))

    print(f"  Level {level}: mode={mode}, mean={mean:.1f}")
    for name, spec in schemes.items():
        wfn = spec['fn']
        e_honest = expected_weight(wfn, pmf)
        g_star, max_wps = max_weight_per_slot(wfn)

        safety_margins = []
        for beta in betas:
            honest_wps = r * (1 - beta) * e_honest
            adv_wps = beta * max_wps
            safety = honest_wps / adv_wps if adv_wps > 0 else float('inf')
            safety_margins.append(safety)

        ax.plot(betas, safety_margins, color=spec['color'],
                linestyle=spec['linestyle'], linewidth=2, label=name)

        # Print at β=0.33
        idx33 = np.argmin(np.abs(betas - 0.33))
        print(f"  {name}: E[w|honest]={e_honest:.4f}, g*={g_star}, "
              f"max_w/g={max_wps:.6f}, safety@β=0.33: {safety_margins[idx33]:.4f}")

    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Break-even')
    ax.axvline(0.33, color='gray', linestyle=':', linewidth=1, alpha=0.5)
    ax.set_xlabel('Adversary fraction β', fontsize=13)
    ax.set_ylabel('Safety margin (honest/adv weight rate)', fontsize=13)
    ax.set_title(f'Consistency Bound: Safety Margin vs Adversary Fraction\n'
                 f'(Level {level}, mode={mode}, mean={mean:.1f}, fill rate r={r})', fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.05, 0.48)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "consistency_bound_comparison.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")
    return mode, mean

# ─── Analysis 3: Fill rate sweep ─────────────────────────────────────────────

def analysis_fillrate_sweep(mode, mean):
    print("\n=== Analysis 3: Fill Rate Sweep ===")

    level = 3
    mp, sc = LEVELS[level]
    pmf = gap_pmf(mp, sc)

    beta = 0.33
    r_values = np.linspace(0.05, 0.50, 50)

    schemes = {
        'Current (w=f^α)': w_current,
        'W3 (σ=0.5)': lambda g: w3(g, mode, mean, 0.5),
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    for name, wfn in schemes.items():
        e_honest_natural = expected_weight(wfn, pmf)
        g_star, max_wps = max_weight_per_slot(wfn)

        ratios = []
        for r in r_values:
            # Scale E[w] linearly with r/r_natural
            scale = r / R_NATURAL
            e_honest = e_honest_natural * scale
            honest_wps = r * (1 - beta) * e_honest
            adv_wps = beta * max_wps
            ratio = honest_wps / adv_wps if adv_wps > 0 else float('inf')
            ratios.append(ratio)

        color = 'tomato' if 'Current' in name else 'steelblue'
        ax.plot(r_values, ratios, linewidth=2, label=name, color=color)

        idx_nat = np.argmin(np.abs(r_values - R_NATURAL))
        print(f"  {name}: ratio@r=0.14: {ratios[idx_nat]:.4f}")

    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Break-even')
    ax.axvline(R_NATURAL, color='gray', linestyle=':', linewidth=1, alpha=0.5,
               label=f'r_natural={R_NATURAL}')
    ax.set_xlabel('Fill rate r', fontsize=13)
    ax.set_ylabel('Honest/Adversary weight rate ratio', fontsize=13)
    ax.set_title(f'Consistency vs Fill Rate (β={beta}, Level {level})', fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "consistency_vs_fillrate.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")

# ─── Analysis 4: Adversary optimal gap ───────────────────────────────────────

def analysis_adversary_gap(sigma_left_factor=0.5):
    print("\n=== Analysis 4: Adversary Optimal Gap ===")

    n_levels = len(LEVELS)
    fig, axes = plt.subplots(1, n_levels, figsize=(5 * n_levels, 5))

    for idx, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ax = axes[idx]

        max_gap_plot = min(int(mean * 6) + 1, 400)
        gaps = np.arange(1, max_gap_plot + 1)

        w3_vals = np.array([w3(g, mode, mean, sigma_left_factor) for g in gaps])
        w3_per_slot = w3_vals / gaps  # w(g)/g

        # Normalize
        w3_per_slot_norm = w3_per_slot / w3_per_slot.max()

        g_star = gaps[np.argmax(w3_per_slot)]
        max_val = w3_per_slot_norm.max()

        ax.plot(gaps, w3_per_slot_norm, 'steelblue', linewidth=2, label='w3(g)/g (norm.)')
        ax.axvline(g_star, color='red', linestyle='--', linewidth=1.5,
                   label=f'g*={g_star} (adv opt)')
        ax.axvline(mode, color='green', linestyle=':', linewidth=1.5,
                   label=f'mode={mode} (honest)')
        ax.axvline(mean, color='orange', linestyle=':', linewidth=1.5,
                   label=f'mean={mean:.1f}')

        ax.set_title(f'Level {level}\nmp={mp}, sc={sc}', fontsize=10)
        ax.set_xlabel('Gap g')
        ax.set_ylabel('w3(g)/g  (normalized)')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        print(f"  Level {level}: mode={mode}, mean={mean:.1f}, g*={g_star}  "
              f"(adv opt delay: {g_star - mode:+d} slots from mode)")

    fig.suptitle(f'Adversary Optimal Gap: w3(g)/g  (σ_left={sigma_left_factor})', fontsize=13)
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "adversary_optimal_gap.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")

# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(sweep_results):
    print("\n" + "=" * 60)
    print("SUMMARY: W3 vs Current Weight Function")
    print("=" * 60)

    beta_target = 0.33
    r = R_NATURAL

    for level, (mp, sc) in LEVELS.items():
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)

        # Current scheme
        e_cur = expected_weight(w_current, pmf)
        g_cur, wps_cur = max_weight_per_slot(w_current)
        sm_cur = (r * (1 - beta_target) * e_cur) / (beta_target * wps_cur)

        # W3 σ=0.5
        wfn_w3 = lambda g, m=mode, mn=mean: w3(g, m, mn, 0.5)
        e_w3 = expected_weight(wfn_w3, pmf)
        g_w3, wps_w3 = max_weight_per_slot(wfn_w3)
        sm_w3 = (r * (1 - beta_target) * e_w3) / (beta_target * wps_w3)

        # PoW reference
        e_pow = 1.0
        g_pow, wps_pow = 1, 1.0
        sm_pow = (r * (1 - beta_target)) / beta_target

        dominates = "✓ W3 > Current" if sm_w3 > sm_cur else "✗ W3 < Current"
        approaches_pow = "≈ PoW" if abs(sm_w3 - sm_pow) / sm_pow < 0.15 else f"gap={abs(sm_w3-sm_pow)/sm_pow*100:.0f}%"

        print(f"\nLevel {level} (mode={mode}, mean={mean:.1f}):")
        print(f"  Current: safety@β=0.33 = {sm_cur:.4f}  (g*={g_cur})")
        print(f"  W3(σ=0.5): safety@β=0.33 = {sm_w3:.4f}  (g*={g_w3})")
        print(f"  PoW ref:  safety@β=0.33 = {sm_pow:.4f}")
        print(f"  → {dominates}  |  W3 vs PoW: {approaches_pow}")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("W3 Plateau Weight Function — Consistency Bound Analysis")
    print("=" * 60)

    sweep_results = analysis_param_sweep()
    mode, mean = analysis_consistency_bounds()
    analysis_fillrate_sweep(mode, mean)
    analysis_adversary_gap()
    print_summary(sweep_results)

    print("\n[Done] All figures saved to paper/analysis/figures/")
