#!/usr/bin/env python3
"""
W3 Hardened Weight Function — Consistency Bound Analysis

Hardens the W3 weight function with a ψ floor: w(g) = 0 for g < PSI = 1,
matching the election threshold dormant period. This kills the burst attack
since the adversary producing blocks at gap=1 gets zero weight AND can't
be elected (threshold=0 from PSI dormant period).

Key questions:
  1. Does the ψ floor push g* (adversary optimal gap) to the mode?
  2. Does hardened W3 track the PoW reference bound more closely?
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from math import exp
import os

# ─── Parameters ───────────────────────────────────────────────────────────────
LEVELS = {
    1: (0.990000, 0.1000),
    2: (0.511239, 1.9973),
    3: (0.215899, 4.0007),
    4: (0.111954, 8.0001),
    5: (0.047830, 16.000),
}
PSI = 1  # dormant period = election threshold
AMPLITUDE, BASELINE, CUTOFF = 0.5, 0.05, 15
ALPHA = 2
R_NATURAL = 0.14

SIGMA_FACTORS = [0.1, 0.25, 0.5]  # focus on tighter values

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

# ─── Weight functions ─────────────────────────────────────────────────────────

def snowplow(slot_gap):
    """LDD snowplow threshold."""
    if slot_gap <= 0:
        return 0.0
    if slot_gap < CUTOFF:
        diff = AMPLITUDE * slot_gap / CUTOFF
    else:
        diff = BASELINE
    return min(diff, 1.0)


def w_current(slot_gap):
    """Current weight: amplified LDD threshold."""
    f = snowplow(slot_gap)
    return f ** ALPHA


def w3_unhardened(gap, mode, mean, sigma_left_factor=0.5):
    """Original W3 without ψ floor (allows burst at gap=1)."""
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


def w3_hardened(gap, mode, mean, sigma_left_factor=0.25):
    """
    W3 with ψ floor: zero weight for gap < PSI, matching the election threshold.
    Left taper rises from 0 at PSI up to 1.0 at mode.
    Plateau from mode to mean.
    Right Gaussian taper beyond mean.
    """
    if gap < PSI:
        return 0.0
    sigma_left = mode * sigma_left_factor
    sigma_right = mean * 0.5
    if gap < mode:
        return exp(-0.5 * ((gap - mode) / sigma_left) ** 2)
    elif gap <= mean:
        return 1.0
    else:
        return exp(-0.5 * ((gap - mean) / sigma_right) ** 2)


# ─── Gap distribution (renewal theory) ───────────────────────────────────────

def shifted_exp_thr(gap, mp, sc):
    """Shifted exponential election threshold for level L."""
    if gap < PSI:
        return 0.0
    return min(1.0, mp * (1.0 - exp(-(gap - PSI) / sc)))


def gap_pmf(mp, sc, max_gap=500):
    """
    Stationary gap distribution under shifted exponential election threshold.
    P(gap = g) ∝ P(elected at g) * P(not elected at 1..g-1)
    """
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


# ─── Analysis 1: Parameter sweep with ψ floor ────────────────────────────────

def analysis_param_sweep():
    print("\n=== Analysis 1: Hardened W3 Parameter Sweep (ψ floor) ===")

    n_levels = len(LEVELS)
    n_sigma = len(SIGMA_FACTORS)

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
        g_star_list = []

        for sf in SIGMA_FACTORS:
            def wfn(g, sf=sf, m=mode, mn=mean):
                return w3_hardened(g, m, mn, sf)

            e_honest = expected_weight(wfn, pmf)

            # Burst: mean w over [PSI, mode-1]; adversary rushing but PSI-floored
            burst_lo = PSI
            burst_hi = max(PSI + 1, mode - 1)
            burst_gaps = list(range(burst_lo, burst_hi + 1))
            e_burst = float(np.mean([wfn(g) for g in burst_gaps])) if burst_gaps else 0.0

            # Delay: mean w over [mean*2, mean*3]
            delay_lo = int(mean * 2)
            delay_hi = int(mean * 3) + 1
            delay_gaps = list(range(delay_lo, delay_hi + 1))
            e_delay = float(np.mean([wfn(g) for g in delay_gaps])) if delay_gaps else 0.0

            # Optimal: adversary picks g* to max w(g)/g; normalized to honest timing
            g_star, max_wps = max_weight_per_slot(wfn)
            e_optimal = max_wps * mean  # adversary per-block weight (normalized)

            best_ratio = e_honest / e_optimal if e_optimal > 0 else float('inf')

            best_ratios.append(best_ratio)
            e_honest_list.append(e_honest)
            e_burst_list.append(e_burst)
            e_delay_list.append(e_delay)
            g_star_list.append(g_star)

        results[level] = {
            'mode': mode, 'mean': mean,
            'best_ratios': best_ratios,
            'e_honest': e_honest_list,
            'e_burst': e_burst_list,
            'e_delay': e_delay_list,
            'g_stars': g_star_list,
        }

        x = np.arange(n_sigma)
        width = 0.2
        ax.bar(x - width, e_honest_list, width, label='E[w|honest]', color='steelblue', alpha=0.8)
        ax.bar(x, e_burst_list, width, label='E[w|burst]', color='tomato', alpha=0.8)
        ax.bar(x + width, e_delay_list, width, label='E[w|delay]', color='orange', alpha=0.8)

        ax2 = ax.twinx()
        ax2.plot(x, best_ratios, 'g^--', linewidth=2, markersize=8, label='best_ratio')
        ax2.axhline(1.0, color='gray', linestyle=':', linewidth=1)
        ax2.set_ylabel('E[w|honest] / E[w|optimal_adv]', color='green')
        ax2.tick_params(axis='y', labelcolor='green')

        # Annotate g* on top
        for i, gs in enumerate(g_star_list):
            ax.annotate(f'g*={gs}', xy=(x[i], max(e_honest_list[i], e_burst_list[i]) + 0.02),
                        ha='center', fontsize=8, color='purple')

        ax.set_title(
            f'Level {level}: mode={mode}, mean={mean:.1f}  (mp={mp}, sc={sc}) — Hardened W3 (ψ={PSI})',
            fontsize=10
        )
        ax.set_xlabel('sigma_left_factor')
        ax.set_ylabel('Expected weight')
        ax.set_xticks(x)
        ax.set_xticklabels([str(s) for s in SIGMA_FACTORS])
        ax.legend(loc='upper left')
        ax2.legend(loc='upper right')

        print(f"\n  Level {level}: mode={mode}, mean={mean:.1f}")
        for i, sf in enumerate(SIGMA_FACTORS):
            print(f"    σ_L={sf}: E[honest]={e_honest_list[i]:.4f}, "
                  f"E[burst]={e_burst_list[i]:.4f}, E[delay]={e_delay_list[i]:.4f}, "
                  f"g*={g_star_list[i]}, ratio={best_ratios[i]:.3f}")

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "hardened_param_sweep.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved: {out}")
    return results


# ─── Analysis 2: Adversary optimal gap under hardened W3 ─────────────────────

def analysis_adversary_optimal():
    print("\n=== Analysis 2: Adversary Optimal Gap (Hardened W3, σ=0.25) ===")

    sf = 0.25
    n_levels = len(LEVELS)
    fig, axes = plt.subplots(1, n_levels, figsize=(5 * n_levels, 5))
    if n_levels == 1:
        axes = [axes]

    for idx, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ax = axes[idx]

        max_gap_plot = min(int(mean * 6) + 1, 400)
        gaps = np.arange(1, max_gap_plot + 1)

        wh_vals = np.array([w3_hardened(g, mode, mean, sf) for g in gaps])
        wh_per_slot = wh_vals / gaps  # w(g)/g

        g_star_idx = int(np.argmax(wh_per_slot))
        g_star = gaps[g_star_idx]

        # Normalize for display
        wh_per_slot_norm = wh_per_slot / wh_per_slot.max() if wh_per_slot.max() > 0 else wh_per_slot

        # Honest gap distribution (normalized for shading)
        honest_pmf = pmf[1:max_gap_plot + 1]
        if honest_pmf.max() > 0:
            honest_pmf_norm = honest_pmf / honest_pmf.max()
        else:
            honest_pmf_norm = honest_pmf

        ax.fill_between(gaps, honest_pmf_norm, alpha=0.2, color='steelblue', label='Honest gap dist.')
        ax.plot(gaps, wh_per_slot_norm, 'royalblue', linewidth=2, label='w₃ₕ(g)/g (norm.)')
        ax.axvline(g_star, color='red', linestyle='--', linewidth=1.5,
                   label=f'g*={g_star} (adv opt)')
        ax.axvline(mode, color='green', linestyle=':', linewidth=1.5,
                   label=f'mode={mode} (honest)')
        ax.axvline(mean, color='orange', linestyle=':', linewidth=1.5,
                   label=f'mean={mean:.1f}')

        rel = g_star - mode
        rel_str = f'{rel:+d}' if rel != 0 else '= mode ✓'
        ax.set_title(f'Level {level}  g*={g_star} ({rel_str} from mode)', fontsize=10)
        ax.set_xlabel('Gap g')
        ax.set_ylabel('Normalized value')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        print(f"  Level {level}: mode={mode}, mean={mean:.1f}, g*={g_star}  "
              f"({'= mode ✓' if g_star == mode else f'offset {g_star - mode:+d} from mode'})")

    fig.suptitle(
        f'Adversary Optimal Gap: w₃ₕ(g)/g  (hardened W3, σ_left={sf}, ψ={PSI})',
        fontsize=13
    )
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "hardened_adversary_optimal.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ─── Analysis 3: Consistency bound comparison (5 schemes) ────────────────────

def analysis_consistency_bounds():
    print("\n=== Analysis 3: Consistency Bound Comparison (5 schemes) ===")

    # Use level 3 as representative
    level = 3
    mp, sc = LEVELS[level]
    pmf = gap_pmf(mp, sc)
    mode, mean = gap_mode_mean(pmf)

    r = R_NATURAL
    betas = np.linspace(0.05, 0.45, 80)

    # Define 5 schemes
    def make_w3u(sf):
        def fn(g): return w3_unhardened(g, mode, mean, sf)
        return fn

    def make_w3h(sf):
        def fn(g): return w3_hardened(g, mode, mean, sf)
        return fn

    schemes = [
        {
            'name': 'Current (w=f²)',
            'fn': w_current,
            'color': 'tomato',
            'linestyle': '-',
        },
        {
            'name': 'W3 unhardened σ=0.5',
            'fn': make_w3u(0.5),
            'color': 'sandybrown',
            'linestyle': '--',
        },
        {
            'name': 'W3 hardened σ=0.25',
            'fn': make_w3h(0.25),
            'color': 'steelblue',
            'linestyle': '-',
        },
        {
            'name': 'W3 hardened σ=0.10',
            'fn': make_w3h(0.10),
            'color': 'royalblue',
            'linestyle': '--',
        },
        {
            'name': 'PoW reference',
            'fn': lambda g: 1.0,
            'color': 'green',
            'linestyle': ':',
        },
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    print(f"  Level {level}: mode={mode}, mean={mean:.1f}")
    for spec in schemes:
        wfn = spec['fn']
        e_honest = expected_weight(wfn, pmf)
        g_star, max_wps = max_weight_per_slot(wfn)

        safety_margins = []
        for beta in betas:
            honest_rate = r * (1 - beta) * e_honest
            adv_rate = beta * max_wps
            safety = honest_rate / adv_rate if adv_rate > 0 else float('inf')
            safety_margins.append(safety)

        ax.plot(betas, safety_margins,
                color=spec['color'], linestyle=spec['linestyle'],
                linewidth=2, label=spec['name'])

        idx33 = int(np.argmin(np.abs(betas - 0.33)))
        print(f"  {spec['name']:30s}: E[w]={e_honest:.4f}, g*={g_star:3d}, "
              f"max_w/g={max_wps:.6f}, safety@β=0.33={safety_margins[idx33]:.4f}")

    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Break-even')
    ax.axvline(0.33, color='gray', linestyle=':', linewidth=1, alpha=0.5, label='β=0.33')
    ax.set_xlabel('Adversary fraction β', fontsize=13)
    ax.set_ylabel('Safety margin (honest/adv weight rate)', fontsize=13)
    ax.set_title(
        f'Consistency Bound: 5-Scheme Comparison\n'
        f'(Level {level}, mode={mode}, mean={mean:.1f}, r={r})',
        fontsize=12
    )
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.05, 0.45)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "hardened_consistency_bound.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")
    return mode, mean


# ─── Analysis 4: Fill rate robustness ────────────────────────────────────────

def analysis_fillrate_robustness(mode, mean):
    print("\n=== Analysis 4: Fill Rate Robustness ===")

    level = 3
    mp, sc = LEVELS[level]
    pmf = gap_pmf(mp, sc)

    beta = 0.33
    r_values = np.linspace(0.05, 0.50, 60)

    schemes = [
        {
            'name': 'Current (w=f²)',
            'fn': w_current,
            'color': 'tomato',
            'linestyle': '-',
        },
        {
            'name': 'W3 hardened σ=0.25',
            'fn': lambda g: w3_hardened(g, mode, mean, 0.25),
            'color': 'steelblue',
            'linestyle': '-',
        },
        {
            'name': 'W3 hardened σ=0.10',
            'fn': lambda g: w3_hardened(g, mode, mean, 0.10),
            'color': 'royalblue',
            'linestyle': '--',
        },
        {
            'name': 'PoW reference',
            'fn': lambda g: 1.0,
            'color': 'green',
            'linestyle': ':',
        },
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    for spec in schemes:
        wfn = spec['fn']
        e_honest = expected_weight(wfn, pmf)
        g_star, max_wps = max_weight_per_slot(wfn)

        ratios = []
        for r in r_values:
            honest_rate = r * (1 - beta) * e_honest
            adv_rate = beta * max_wps
            ratio = honest_rate / adv_rate if adv_rate > 0 else float('inf')
            ratios.append(ratio)

        ax.plot(r_values, ratios,
                color=spec['color'], linestyle=spec['linestyle'],
                linewidth=2, label=spec['name'])

        idx_nat = int(np.argmin(np.abs(r_values - R_NATURAL)))
        print(f"  {spec['name']:30s}: ratio@r=0.14={ratios[idx_nat]:.4f}")

    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='Break-even')
    ax.axvline(R_NATURAL, color='gray', linestyle=':', linewidth=1, alpha=0.5,
               label=f'r_natural={R_NATURAL}')
    ax.set_xlabel('Fill rate r', fontsize=13)
    ax.set_ylabel('Safety margin (honest/adv weight rate)', fontsize=13)
    ax.set_title(
        f'Fill Rate Robustness — Hardened W3 vs Schemes\n'
        f'(β={beta}, Level {level}, mode={mode}, mean={mean:.1f})',
        fontsize=12
    )
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "hardened_fillrate_robustness.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ─── Analysis 5: Summary table ────────────────────────────────────────────────

def analysis_summary_table():
    print("\n=== HARDENED W3 vs CURRENT vs PoW at β=0.33 ===")

    beta = 0.33
    r = R_NATURAL

    def get_safety(wfn, pmf, mean_gap):
        e_honest = expected_weight(wfn, pmf)
        g_star, max_wps = max_weight_per_slot(wfn)
        honest_rate = r * (1 - beta) * e_honest
        adv_rate = beta * max_wps
        safety = honest_rate / adv_rate if adv_rate > 0 else float('inf')
        return safety, g_star

    # Compute g* at level 3 for all schemes
    mp3, sc3 = LEVELS[3]
    pmf3 = gap_pmf(mp3, sc3)
    mode3, mean3 = gap_mode_mean(pmf3)

    g_cur = max_weight_per_slot(w_current)[0]
    g_w3u = max_weight_per_slot(lambda g: w3_unhardened(g, mode3, mean3, 0.5))[0]
    g_w3h25 = max_weight_per_slot(lambda g: w3_hardened(g, mode3, mean3, 0.25))[0]
    g_w3h10 = max_weight_per_slot(lambda g: w3_hardened(g, mode3, mean3, 0.10))[0]

    rows = {
        'Current        ': {'fn_maker': lambda m, mn: w_current, 'g_star_l3': g_cur},
        'W3-unhardened  ': {'fn_maker': lambda m, mn: (lambda g: w3_unhardened(g, m, mn, 0.5)), 'g_star_l3': g_w3u},
        'W3-hard-σ0.25  ': {'fn_maker': lambda m, mn: (lambda g: w3_hardened(g, m, mn, 0.25)), 'g_star_l3': g_w3h25},
        'W3-hard-σ0.10  ': {'fn_maker': lambda m, mn: (lambda g: w3_hardened(g, m, mn, 0.10)), 'g_star_l3': g_w3h10},
        'PoW ref        ': {'fn_maker': lambda m, mn: (lambda g: 1.0), 'g_star_l3': 'N/A'},
    }

    header = f"{'Scheme':16s}| {'L1':5s} | {'L2':5s} | {'L3':5s} | {'L4':5s} | {'L5':5s} | g*(L3)"
    sep    = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for scheme_name, spec in rows.items():
        safeties = []
        for level, (mp, sc) in LEVELS.items():
            pmf = gap_pmf(mp, sc)
            mode, mean = gap_mode_mean(pmf)
            wfn = spec['fn_maker'](mode, mean)
            s, _ = get_safety(wfn, pmf, mean)
            safeties.append(s)

        g_str = str(spec['g_star_l3'])
        row = (f"{scheme_name:16s}| "
               f"{safeties[0]:5.2f} | {safeties[1]:5.2f} | {safeties[2]:5.2f} | "
               f"{safeties[3]:5.2f} | {safeties[4]:5.2f} | {g_str}")
        print(row)

    print(sep)
    print(f"\n  (L3 mode={mode3}, ψ={PSI})")
    print(f"  g* for hardened σ=0.25: {g_w3h25}  ({'= mode ✓' if g_w3h25 == mode3 else f'offset {g_w3h25 - mode3:+d}'})")
    print(f"  g* for hardened σ=0.10: {g_w3h10}  ({'= mode ✓' if g_w3h10 == mode3 else f'offset {g_w3h10 - mode3:+d}'})")

    return {
        'mode3': mode3, 'mean3': mean3,
        'g_cur': g_cur, 'g_w3u': g_w3u,
        'g_w3h25': g_w3h25, 'g_w3h10': g_w3h10,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("W3 Hardened Weight Function — Consistency Bound Analysis")
    print("=" * 60)
    print(f"ψ floor = {PSI}  (election threshold dormant period)")
    print(f"Sigma factors: {SIGMA_FACTORS}")
    print("=" * 60)

    sweep_results = analysis_param_sweep()
    analysis_adversary_optimal()
    mode, mean = analysis_consistency_bounds()
    analysis_fillrate_robustness(mode, mean)
    summary = analysis_summary_table()

    print("\n[Done] All figures saved to paper/analysis/figures/")
    print(f"Key result: g* (adv optimal) for hardened W3 σ=0.25 at L3 = {summary['g_w3h25']} "
          f"(mode={summary['mode3']})")
