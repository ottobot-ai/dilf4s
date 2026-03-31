#!/usr/bin/env python3
"""
Ramp Weight Function — Path to PoW Consistency Bound

The ramp weight function w_ramp(g) achieves a CONSTANT w(g)/g for all g in [PSI, mean].
This eliminates any adversarial timing advantage — only stake fraction β matters.

Key insight:
    w_ramp(g)/g = 1/mean  (constant for PSI ≤ g ≤ mean)
→ Adversary's optimal strategy: pick ANY g in [PSI, mean] — they all give the same w/g.
→ Security condition: (1-β)*E[w|honest] > β  →  β < 0.5 when E[w|honest] = 1 (PoW bound).

Compare vs:
    - Current scheme (f²): adversary picks g*=14, breaks at β≈0.30
    - W3 hardened σ=0.25: g*≈mode, breaks at β≈0.32
    - PoW reference: (1-β)/β — theoretical maximum
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
PSI = 1          # election threshold dormant period
AMPLITUDE, BASELINE, CUTOFF = 0.5, 0.05, 15
ALPHA = 2

FIGURES_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)


# ─── Weight functions ─────────────────────────────────────────────────────────

def w_ramp(gap, mean, sigma_right_factor=0.5):
    """
    Ramp weight function — designed to equalize w(g)/g across all sub-mean gaps.

    g < PSI:          w = 0          (matches election threshold dormant period)
    PSI ≤ g ≤ mean:   w = g/mean     (linear ramp — w/g = 1/mean, CONSTANT)
    g > mean:         w = exp(-0.5 * ((g - mean) / (mean * sigma_right_factor))**2)
                                     (Gaussian decay — prevents delay gaming)
    """
    if gap < PSI:
        return 0.0
    elif gap <= mean:
        return gap / mean
    else:
        sigma_right = mean * sigma_right_factor
        return exp(-0.5 * ((gap - mean) / sigma_right) ** 2)


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
    """Current weight: amplified LDD threshold (f²)."""
    f = snowplow(slot_gap)
    return f ** ALPHA


def w3_hardened(gap, mode, mean, sigma_left_factor=0.25):
    """
    W3 hardened: ψ floor + Gaussian left taper + plateau + right taper.
    Best existing scheme for reference.
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
    """Shifted exponential election threshold."""
    if gap < PSI:
        return 0.0
    return min(1.0, mp * (1.0 - exp(-(gap - PSI) / sc)))


def gap_pmf(mp, sc, max_gap=800):
    """Stationary gap distribution P(gap = g) under shifted exponential election."""
    pmf = np.zeros(max_gap + 1)
    survival = 1.0
    for g in range(1, max_gap + 1):
        h = shifted_exp_thr(g, mp, sc)
        pmf[g] = h * survival
        survival *= (1.0 - h)
        if survival < 1e-14:
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
    """E[w | honest] using renewal-theory gap pmf."""
    total = 0.0
    for g in range(len(pmf)):
        if pmf[g] > 1e-16:
            total += w_fn(g) * pmf[g]
    return total


def max_weight_per_slot(w_fn, max_gap=600):
    """
    Adversary optimal: find g* = argmax w(g)/g.
    Returns (g*, max w(g)/g).
    """
    best_val = 0.0
    best_g = PSI
    for g in range(PSI, max_gap + 1):
        if g == 0:
            continue
        val = w_fn(g) / g
        if val > best_val:
            best_val = val
            best_g = g
    return best_g, best_val


def safety_margin_fn(wfn, pmf, mean, beta):
    """
    Unified safety margin formula:
        safety = (1-β) * E[w|honest] / (β * mean * max_wps)

    Derivation:
        honest_weight_rate = (1-β) * (1/mean) * E[w|honest]   [honest block rate = 1/mean]
        adv_weight_rate    = β * max_wps                       [adversary picks g* to max w/g]
        safety = honest / adv = (1-β) * E[w|honest] / (β * mean * max_wps)

    For ramp: max_wps = 1/mean → safety = (1-β) * E[w|honest] / β  → PoW bound when E[w]=1.
    """
    e_honest = expected_weight(wfn, pmf)
    g_star, max_wps = max_weight_per_slot(wfn)
    if max_wps == 0 or beta == 0:
        return float('inf')
    return (1 - beta) * e_honest / (beta * mean * max_wps)


# ─── Analysis 1: w_ramp(g)/g — verifying constant property ──────────────────

def analysis_weight_per_slot():
    print("\n=== Analysis 1: Verify constant w(g)/g property for ramp ===")

    n_levels = len(LEVELS)
    fig, axes = plt.subplots(n_levels, 1, figsize=(12, 4 * n_levels))
    if n_levels == 1:
        axes = [axes]

    for idx, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ax = axes[idx]

        max_gap_plot = min(int(mean * 5) + 5, 300)
        gaps = np.arange(1, max_gap_plot + 1)

        def wfn(g): return w_ramp(g, mean, sigma_right_factor=0.5)

        w_vals = np.array([wfn(g) for g in gaps])
        w_per_slot = np.array([wfn(g) / g for g in gaps])  # w(g)/g

        # theoretical flat value in ramp region
        flat_val = 1.0 / mean

        # Honest gap distribution (scale for visibility)
        honest_pmf = pmf[1:max_gap_plot + 1]
        scale_factor = flat_val / honest_pmf.max() if honest_pmf.max() > 0 else 1.0
        honest_scaled = honest_pmf * scale_factor

        # Find where w/g is maximized
        g_star_idx = int(np.argmax(w_per_slot))
        g_star = gaps[g_star_idx]
        max_wps = w_per_slot[g_star_idx]

        # Plot
        ax2 = ax.twinx()
        ax.fill_between(gaps, honest_scaled, alpha=0.15, color='steelblue', label='Honest gap dist (scaled)')
        ax.plot(gaps, w_vals, 'steelblue', linewidth=1.5, alpha=0.7, label='w_ramp(g)')

        ax2.plot(gaps, w_per_slot, 'darkred', linewidth=2, label='w_ramp(g)/g')
        ax2.axhline(flat_val, color='orange', linestyle='--', linewidth=1.5,
                    label=f'1/mean = {flat_val:.4f} (flat target)')

        ax.axvline(mode, color='green', linestyle=':', linewidth=1.5, label=f'mode={mode}')
        ax.axvline(mean, color='purple', linestyle=':', linewidth=1.5, label=f'mean={mean:.1f}')

        # Check: is w/g flat in [PSI, mean]?
        ramp_region = gaps[(gaps >= PSI) & (gaps <= int(mean))]
        if len(ramp_region) > 0:
            wps_ramp = np.array([wfn(g) / g for g in ramp_region])
            max_dev = np.max(np.abs(wps_ramp - flat_val))
            flat_ok = "✓ FLAT" if max_dev < 1e-10 else f"⚠ max_dev={max_dev:.2e}"
        else:
            flat_ok = "N/A"

        # g* location
        if g_star <= int(mean):
            g_star_loc = f"in ramp [PSI,mean] {flat_ok}"
        else:
            g_star_loc = f"above mean (delay gaming!)"

        ax.set_title(
            f'Level {level}: mode={mode}, mean={mean:.1f} | '
            f'g*={g_star} ({g_star_loc})',
            fontsize=10
        )
        ax.set_xlabel('Gap g')
        ax.set_ylabel('w_ramp(g)', color='steelblue')
        ax2.set_ylabel('w_ramp(g)/g', color='darkred')
        ax2.tick_params(axis='y', labelcolor='darkred')

        # Combine legends
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')
        ax.grid(True, alpha=0.3)

        print(f"  Level {level}: mode={mode}, mean={mean:.1f}, "
              f"flat_val=1/mean={flat_val:.4f}, g*={g_star}, max_wps={max_wps:.6f}, "
              f"ramp region: {flat_ok}")

    fig.suptitle(
        'Ramp Weight Function: w(g)/g Verification\n'
        'Orange dashed = 1/mean (constant target) — flat in [PSI, mean] eliminates timing advantage',
        fontsize=13
    )
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "ramp_weight_per_slot.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ─── Analysis 2: E[w|honest] comparison ──────────────────────────────────────

def analysis_ew_comparison():
    print("\n=== Analysis 2: E[w|honest] comparison — Ramp vs W3-hardened vs Current ===")

    results = {}
    header = f"{'Level':>6} | {'mode':>5} | {'mean':>6} | {'E[w|cur]':>9} | {'E[w|W3h]':>9} | {'E[w|ramp0.5]':>12} | {'E[w|ramp0.25]':>13} | {'loss vs W3h (ramp0.5)':>22}"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for level, (mp, sc) in LEVELS.items():
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)

        ew_cur = expected_weight(w_current, pmf)
        ew_w3h = expected_weight(lambda g, m=mode, mn=mean: w3_hardened(g, m, mn, 0.25), pmf)
        ew_ramp05 = expected_weight(lambda g, mn=mean: w_ramp(g, mn, 0.5), pmf)
        ew_ramp025 = expected_weight(lambda g, mn=mean: w_ramp(g, mn, 0.25), pmf)

        loss = ew_ramp05 - ew_w3h
        loss_pct = 100 * loss / ew_w3h if ew_w3h > 0 else 0

        results[level] = {
            'mode': mode, 'mean': mean,
            'ew_cur': ew_cur, 'ew_w3h': ew_w3h,
            'ew_ramp05': ew_ramp05, 'ew_ramp025': ew_ramp025,
        }

        print(f"  L{level}   | {mode:>5} | {mean:>6.1f} | {ew_cur:>9.4f} | {ew_w3h:>9.4f} | "
              f"{ew_ramp05:>12.4f} | {ew_ramp025:>13.4f} | {loss:>+.4f} ({loss_pct:>+.1f}%)")

    print(sep)
    print("\n  NOTE: Ramp penalizes early honest blocks (gap < mode gets w=gap/mean < 1)")
    print("  W3 hardened: plateau at 1 from mode to mean (full weight for timely blocks)")
    print("  PoW bound achieved when E[w|honest] → 1.0\n")

    return results


# ─── Analysis 3: Full consistency bound comparison ────────────────────────────

def analysis_consistency_bounds(ew_results):
    print("\n=== Analysis 3: Full Consistency Bound Comparison (all levels) ===")

    betas = np.linspace(0.05, 0.45, 100)
    beta_33 = 0.33

    # For table: safety at β=0.33 per level per scheme
    table = {
        'current': [],
        'w3h_025': [],
        'ramp_05': [],
        'ramp_025': [],
    }

    for level, (mp, sc) in LEVELS.items():
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)

        def wfn_cur(g): return w_current(g)
        def wfn_w3h(g): return w3_hardened(g, mode, mean, 0.25)
        def wfn_r05(g): return w_ramp(g, mean, 0.5)
        def wfn_r025(g): return w_ramp(g, mean, 0.25)

        for key, wfn in [('current', wfn_cur), ('w3h_025', wfn_w3h),
                         ('ramp_05', wfn_r05), ('ramp_025', wfn_r025)]:
            sm = safety_margin_fn(wfn, pmf, mean, beta_33)
            table[key].append(sm)

    # Print summary table
    print("\n" + "=" * 75)
    print(f"=== CONSISTENCY BOUNDS AT β={beta_33} ===")
    print("=" * 75)
    header = f"{'Scheme':<24}| {'L1':>6} | {'L2':>6} | {'L3':>6} | {'L4':>6} | {'L5':>6} | Binding"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    scheme_names = {
        'current':   'Current (f²)',
        'w3h_025':   'W3 hardened σ=0.25',
        'ramp_05':   'Ramp σ_right=0.5',
        'ramp_025':  'Ramp σ_right=0.25',
    }

    scheme_results = {}
    for key, name in scheme_names.items():
        vals = table[key]
        binding_level = int(np.argmin(vals)) + 1
        binding_val = min(vals)
        # Estimate bound: find largest β where all levels have margin > 1
        # (quick approximation: use binding level)
        print(f"  {name:<22}| {vals[0]:>6.2f} | {vals[1]:>6.2f} | {vals[2]:>6.2f} | "
              f"{vals[3]:>6.2f} | {vals[4]:>6.2f} | L{binding_level} (min={binding_val:.2f})")
        scheme_results[key] = {'vals': vals, 'binding': binding_level, 'min': binding_val}

    # PoW reference
    pow_val = (1 - beta_33) / beta_33
    print(f"  {'PoW reference':<22}| {pow_val:>6.2f} | {pow_val:>6.2f} | {pow_val:>6.2f} | "
          f"{pow_val:>6.2f} | {pow_val:>6.2f} | β<0.50")
    print(sep)

    # E[w|honest] table
    print(f"\n  E[w|honest]:")
    print(f"  {'Scheme':<24}| {'L1':>6} | {'L2':>6} | {'L3':>6} | {'L4':>6} | {'L5':>6}")
    print(sep)
    for key, name in [('w3h_025', 'W3 hardened σ=0.25'), ('ramp_05', 'Ramp σ_right=0.5'),
                      ('ramp_025', 'Ramp σ_right=0.25')]:
        ews = [ew_results[lv][f'ew_{"w3h" if key=="w3h_025" else "ramp05" if key=="ramp_05" else "ramp025"}']
               for lv in sorted(LEVELS.keys())]
        print(f"  {name:<22}| {ews[0]:>6.3f} | {ews[1]:>6.3f} | {ews[2]:>6.3f} | "
              f"{ews[3]:>6.3f} | {ews[4]:>6.3f}")
    print(sep)

    # ─── Plot: Full consistency bound curves ─────────────────────────────────
    # Main figure: per-level safety margin vs β for all schemes
    n_levels = len(LEVELS)
    fig, axes = plt.subplots(1, n_levels, figsize=(5 * n_levels, 6), sharey=True)

    plot_schemes = [
        {'key': 'current',  'label': 'Current (f²)',       'color': 'tomato',    'ls': '-'},
        {'key': 'w3h_025',  'label': 'W3 hardened σ=0.25', 'color': 'steelblue', 'ls': '--'},
        {'key': 'ramp_05',  'label': 'Ramp σ_right=0.5',   'color': 'darkgreen', 'ls': '-'},
        {'key': 'ramp_025', 'label': 'Ramp σ_right=0.25',  'color': 'limegreen', 'ls': '--'},
    ]

    for idx, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ax = axes[idx]

        # PoW reference
        pow_margins = (1 - betas) / betas
        ax.plot(betas, pow_margins, 'k:', linewidth=2, label='PoW ref' if idx == 0 else None)

        for spec in plot_schemes:
            key = spec['key']
            if key == 'current':
                wfn = w_current
            elif key == 'w3h_025':
                wfn = lambda g, m=mode, mn=mean: w3_hardened(g, m, mn, 0.25)
            elif key == 'ramp_05':
                wfn = lambda g, mn=mean: w_ramp(g, mn, 0.5)
            else:
                wfn = lambda g, mn=mean: w_ramp(g, mn, 0.25)

            margins = [safety_margin_fn(wfn, pmf, mean, b) for b in betas]
            ax.plot(betas, margins, color=spec['color'], linestyle=spec['ls'],
                    linewidth=2, label=spec['label'] if idx == 0 else None)

        ax.axhline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.6)
        ax.axvline(0.33, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax.set_title(f'Level {level}\nmode={mode}, mean={mean:.1f}', fontsize=10)
        ax.set_xlabel('Adversary β', fontsize=11)
        if idx == 0:
            ax.set_ylabel('Safety margin', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0.05, 0.45)
        ax.set_ylim(0, None)

    # Shared legend
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=5, fontsize=10,
               bbox_to_anchor=(0.5, 1.03))
    fig.suptitle(
        'Consistency Bound: Ramp vs Current vs W3-Hardened vs PoW Reference\n'
        'safety_margin = (1-β)·E[w|honest] / (β·mean·max_wps)',
        fontsize=13, y=1.06
    )
    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "ramp_consistency_bound.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\n  Saved: {out}")

    return scheme_results


# ─── Analysis 4: Efficiency-security tradeoff ─────────────────────────────────

def analysis_efficiency_tradeoff(ew_results):
    print("\n=== Analysis 4: Efficiency-Security Tradeoff ===")
    print("  E[w|honest] per level: ramp penalizes early blocks; W3 plateau gives full weight")

    levels = sorted(LEVELS.keys())
    ew_w3h   = [ew_results[l]['ew_w3h']    for l in levels]
    ew_r05   = [ew_results[l]['ew_ramp05'] for l in levels]
    ew_r025  = [ew_results[l]['ew_ramp025'] for l in levels]
    modes    = [ew_results[l]['mode']       for l in levels]
    means    = [ew_results[l]['mean']       for l in levels]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: E[w|honest] vs level
    ax = axes[0]
    x = np.array(levels)
    ax.plot(x, ew_w3h,  'steelblue', marker='s', linewidth=2, markersize=8, label='W3 hardened σ=0.25')
    ax.plot(x, ew_r05,  'darkgreen', marker='o', linewidth=2, markersize=8, label='Ramp σ_right=0.5')
    ax.plot(x, ew_r025, 'limegreen', marker='^', linewidth=2, markersize=8, linestyle='--',
            label='Ramp σ_right=0.25')
    ax.axhline(1.0, color='black', linestyle=':', linewidth=1.5, label='E[w]=1 (PoW efficiency)')
    ax.set_xlabel('Level', fontsize=12)
    ax.set_ylabel('E[w | honest]', fontsize=12)
    ax.set_title('Honest Block Efficiency: E[w|honest]\n'
                 'Ramp trades efficiency for PoW-level security', fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(x)
    ax.set_ylim(0, 1.15)

    # Annotate fraction of PoW efficiency
    for i, l in enumerate(levels):
        frac = ew_r05[i] / 1.0  # E[w|honest] / 1 (PoW would give 1)
        ax.annotate(f'{frac:.2f}', xy=(l, ew_r05[i]),
                    xytext=(0, 8), textcoords='offset points',
                    ha='center', fontsize=8, color='darkgreen')

    # Right: w_ramp shape for each level (normalized)
    ax2 = axes[1]
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(levels)))
    for i, (level, (mp, sc)) in enumerate(LEVELS.items()):
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        max_gap_plot = min(int(mean * 4) + 5, 200)
        gaps = np.arange(1, max_gap_plot + 1)
        w_vals = np.array([w_ramp(g, mean, 0.5) for g in gaps])
        ax2.plot(gaps, w_vals, color=colors[i], linewidth=2,
                 label=f'L{level} (mode={mode}, mean={mean:.1f})')
        ax2.axvline(mean, color=colors[i], linestyle=':', alpha=0.5)

    ax2.set_xlabel('Gap g (slots)', fontsize=12)
    ax2.set_ylabel('w_ramp(g)', fontsize=12)
    ax2.set_title('Ramp Weight Function Shape per Level\n'
                  'Dashed = mean (ramp peak, right decay starts)', fontsize=11)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, None)

    fig.tight_layout()
    out = os.path.join(FIGURES_DIR, "ramp_efficiency_tradeoff.png")
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")

    # Detailed comparison
    print(f"\n  {'Level':>6} | {'mode':>5} | {'mean':>6} | {'E[w|W3h]':>9} | "
          f"{'E[w|ramp05]':>11} | {'PoW frac':>9} | {'loss vs W3h':>12}")
    sep = "-" * 78
    print(sep)
    for i, level in enumerate(levels):
        frac = ew_r05[i]  # fraction of PoW (E[w]/1)
        loss = ew_r05[i] - ew_w3h[i]
        print(f"  L{level}    | {modes[i]:>5} | {means[i]:>6.1f} | {ew_w3h[i]:>9.4f} | "
              f"{ew_r05[i]:>11.4f} | {frac:>9.4f} | {loss:>+.4f} ({100*loss/ew_w3h[i]:>+.1f}%)")
    print(sep)


# ─── Analysis 5: Detailed per-level adversary g* analysis ────────────────────

def analysis_adversary_gstar():
    print("\n=== Analysis 5: Adversary Optimal g* Under Ramp ===")
    print("  Expected: g* can be ANYWHERE in [PSI, mean] — all give same w/g = 1/mean")

    for level, (mp, sc) in LEVELS.items():
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        flat_val = 1.0 / mean

        # Compute g* for each scheme at this level
        g_cur, wps_cur = max_weight_per_slot(w_current)
        g_w3h, wps_w3h = max_weight_per_slot(lambda g: w3_hardened(g, mode, mean, 0.25))
        g_r05, wps_r05 = max_weight_per_slot(lambda g: w_ramp(g, mean, 0.5))
        g_r025, wps_r025 = max_weight_per_slot(lambda g: w_ramp(g, mean, 0.25))

        # For ramp: verify w(g*)/g* == 1/mean
        ramp_wps_check = w_ramp(g_r05, mean, 0.5) / g_r05 if g_r05 > 0 else 0
        flat_match = "✓ = 1/mean" if abs(ramp_wps_check - flat_val) < 1e-10 else f"≠ 1/mean ({ramp_wps_check:.6f})"

        print(f"  L{level}: mode={mode}, mean={mean:.1f}, 1/mean={flat_val:.5f}")
        print(f"    Current:       g*={g_cur:3d}, max_wps={wps_cur:.6f}")
        print(f"    W3h σ=0.25:    g*={g_w3h:3d}, max_wps={wps_w3h:.6f}")
        print(f"    Ramp σ=0.5:    g*={g_r05:3d}, max_wps={wps_r05:.6f}  {flat_match}")
        print(f"    Ramp σ=0.25:   g*={g_r025:3d}, max_wps={wps_r025:.6f}")
        print()


# ─── Summary and key questions ────────────────────────────────────────────────

def print_summary(ew_results, scheme_results):
    print("\n" + "=" * 75)
    print("=== SUMMARY: Does Ramp Achieve the PoW Consistency Bound? ===")
    print("=" * 75)

    levels = sorted(LEVELS.keys())

    # 1. E[w|honest] per level for ramp
    print("\n1. E[w|honest] per level (ramp σ_right=0.5):")
    ews_ramp = [ew_results[l]['ew_ramp05'] for l in levels]
    for l, ew in zip(levels, ews_ramp):
        print(f"   Level {l}: E[w|honest] = {ew:.4f}  (PoW fraction: {ew:.4f}/1.00 = {100*ew:.1f}%)")
    print(f"   Average: {np.mean(ews_ramp):.4f}")

    print("\n2. Full summary table at β=0.33:")
    # Already printed in analysis_3, just summarize binding
    for key, name in [('current', 'Current (f²)'), ('w3h_025', 'W3 hardened σ=0.25'),
                      ('ramp_05', 'Ramp σ_right=0.5'), ('ramp_025', 'Ramp σ_right=0.25')]:
        if key in scheme_results:
            r = scheme_results[key]
            print(f"   {name:<24}: min={r['min']:.3f} at L{r['binding']}  "
                  f"({'β<0.50 PoW bound' if r['min'] > 2.0 else f'β<0.{int(33*r[chr(109)+chr(105)+chr(110)])//10}?' if r['min'] > 1 else 'INSECURE at β=0.33'})")

    print("\n3. Does ramp achieve the PoW bound?")
    ews_ramp_arr = np.array(ews_ramp)
    avg_ew = np.mean(ews_ramp_arr)
    min_ew = np.min(ews_ramp_arr)
    if avg_ew > 0.95:
        print(f"   ✓ YES — E[w|honest] ≈ {avg_ew:.3f} (mean), min={min_ew:.3f}")
        print(f"   → safety_margin ≈ {avg_ew:.3f} * (1-β)/β  (tracks PoW at {100*avg_ew:.0f}%)")
    else:
        print(f"   ~ APPROACHES — E[w|honest] ≈ {avg_ew:.3f} (mean), min={min_ew:.3f}")
        print(f"   → safety_margin ≈ {avg_ew:.3f} * (1-β)/β  (achieves {100*avg_ew:.0f}% of PoW bound)")
    print(f"   → The {100*(1-avg_ew):.1f}% efficiency loss comes from honest blocks at gap < mode")
    print(f"      getting w = gap/mean < 1 (ramp penalty for early arrival)")

    print("\n4. Binding constraint:")
    if 'ramp_05' in scheme_results:
        r = scheme_results['ramp_05']
        l_bind = r['binding']
        mp_b, sc_b = LEVELS[l_bind]
        pmf_b = gap_pmf(mp_b, sc_b)
        mode_b, mean_b = gap_mode_mean(pmf_b)
        print(f"   Binding level: L{l_bind} (mode={mode_b}, mean={mean_b:.1f})")
        print(f"   Min safety_margin at β=0.33: {r['min']:.3f}")
        ew_bind = ew_results[l_bind]['ew_ramp05']
        beta_bound_approx = ew_bind / (1 + ew_bind)
        print(f"   E[w|honest] at L{l_bind}: {ew_bind:.4f}")
        print(f"   Approx β bound (safety=1 → β < E[w]/(1+E[w])): β < {beta_bound_approx:.3f}")

    print("\n5. Ramp vs W3-hardened at L3 (previously binding level):")
    ew_w3h_l3 = ew_results[3]['ew_w3h']
    ew_ramp_l3 = ew_results[3]['ew_ramp05']
    sm_w3h_l3 = scheme_results['w3h_025']['vals'][2] if 'w3h_025' in scheme_results else None
    sm_ramp_l3 = scheme_results['ramp_05']['vals'][2] if 'ramp_05' in scheme_results else None

    if sm_w3h_l3 and sm_ramp_l3:
        better = "Ramp" if sm_ramp_l3 > sm_w3h_l3 else "W3-hardened"
        print(f"   W3-hardened σ=0.25: E[w]={ew_w3h_l3:.4f}, safety@β=0.33={sm_w3h_l3:.3f}")
        print(f"   Ramp σ_right=0.5:   E[w]={ew_ramp_l3:.4f}, safety@β=0.33={sm_ramp_l3:.3f}")
        print(f"   → {better} is STRICTLY BETTER at L3")
        print(f"   → Ramp improvement: {sm_ramp_l3 - sm_w3h_l3:+.3f} ({100*(sm_ramp_l3/sm_w3h_l3 - 1):+.1f}%)")

    print("\n" + "=" * 75)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Ramp Weight Function — Path to PoW Consistency Bound")
    print("=" * 75)
    print(f"ψ floor = {PSI}  (election threshold dormant period)")
    print(f"Key claim: w_ramp(g)/g = 1/mean for all g in [PSI, mean] → PoW-level security")
    print("=" * 75)

    analysis_weight_per_slot()
    ew_results_raw = analysis_ew_comparison()

    # Repackage ew_results for downstream use
    ew_results = {}
    for level, (mp, sc) in LEVELS.items():
        pmf = gap_pmf(mp, sc)
        mode, mean = gap_mode_mean(pmf)
        ew_results[level] = {
            'mode': mode, 'mean': mean,
            'ew_cur':    expected_weight(w_current, pmf),
            'ew_w3h':    expected_weight(lambda g, m=mode, mn=mean: w3_hardened(g, m, mn, 0.25), pmf),
            'ew_ramp05': expected_weight(lambda g, mn=mean: w_ramp(g, mn, 0.5), pmf),
            'ew_ramp025': expected_weight(lambda g, mn=mean: w_ramp(g, mn, 0.25), pmf),
        }

    scheme_results = analysis_consistency_bounds(ew_results)
    analysis_efficiency_tradeoff(ew_results)
    analysis_adversary_gstar()
    print_summary(ew_results, scheme_results)

    print("\n[Done] All figures saved to paper/analysis/figures/")
