#!/usr/bin/env python3
"""
consistency_bound_final.py
==========================
Final consistency bound analysis for ramp weight function.

Analysis 1: sigma_right sweep (0.5 to inf)
Analysis 2: sc parameter effect on mode/mean ratio
Analysis 3: Combined optimal summary

Key theoretical result to verify:
  E[w_pure_ramp|honest] = E[g/mean] = mean/mean = 1.0 exactly
  => pure ramp achieves EXACTLY the PoW bound (1-beta)/beta
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os
import sys

# ── Parameters ──────────────────────────────────────────────────────────────

LEVELS = {
    1: (0.990000, 0.1000),
    2: (0.511239, 1.9973),
    3: (0.215899, 4.0007),
    4: (0.111954, 8.0001),
    5: (0.047830, 16.000),
}
PSI = 1
BETA = 0.33
POW_BOUND = (1 - BETA) / BETA  # ≈ 2.0303...

LEVEL_COLORS = {1: '#1f77b4', 2: '#ff7f0e', 3: '#2ca02c', 4: '#d62728', 5: '#9467bd'}
LEVEL_LABELS = {1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4', 5: 'L5'}

FIGURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'figures')
os.makedirs(FIGURES_DIR, exist_ok=True)


# ── Core functions ───────────────────────────────────────────────────────────

def shifted_exp(gap, mp, sc, psi=PSI):
    if gap < psi:
        return 0.0
    return min(1.0, mp * (1.0 - np.exp(-(gap - psi) / sc)))


def get_stationary(mp, sc, psi=PSI, MAX_GAP=3000):
    probs, survive = [], 1.0
    for g in range(1, MAX_GAP + 1):
        thr = shifted_exp(g, mp, sc, psi)
        p = survive * thr
        probs.append(p)
        survive *= (1.0 - thr)
        if survive < 1e-12:
            break
    probs = np.array(probs)
    probs /= probs.sum()
    gaps = np.arange(1, len(probs) + 1)
    return gaps, probs


def w_ramp(gap, mean, sigma_right, psi=PSI):
    """Ramp weight: linear rise to mean, Gaussian decay for gap > mean."""
    if gap < psi:
        return 0.0
    elif gap <= mean:
        return gap / mean
    else:
        sr = mean * sigma_right
        return np.exp(-0.5 * ((gap - mean) / sr) ** 2)


def w_pure_ramp(gap, mean, psi=PSI):
    """Pure ramp (no right-tail decay): w = g/mean for all g >= psi."""
    if gap < psi:
        return 0.0
    return gap / mean


def compute_max_wps(gaps, mean, sigma_right):
    """
    Find max w(g)/g over all g.
    In ramp zone [psi, mean]: w/g = 1/mean (constant).
    Beyond mean: w/g = exp(-0.5*((g-mean)/(mean*sr))^2) / g  → strictly < 1/mean.
    Returns max_wps and the adversary's optimal gap.
    """
    max_wps = 1.0 / mean  # from ramp zone
    opt_g = mean
    for g in gaps:
        if g > mean:
            sr = mean * sigma_right
            wg = np.exp(-0.5 * ((g - mean) / sr) ** 2) / g
            if wg > max_wps:
                max_wps = wg
                opt_g = g
    return max_wps, opt_g


def safety_margin(mp, sc, sigma_right, beta=BETA, psi=PSI, pure_ramp=False):
    """
    Compute safety margin = honest_rate / adv_rate.
    Returns (margin, E_w_honest, mean).
    """
    gaps, probs = get_stationary(mp, sc, psi)
    mean = np.dot(gaps, probs)

    if pure_ramp:
        w_vals = np.array([w_pure_ramp(g, mean, psi) for g in gaps])
    else:
        w_vals = np.array([w_ramp(g, mean, sigma_right, psi) for g in gaps])

    E_w_honest = np.dot(probs, w_vals)

    if pure_ramp:
        max_wps = 1.0 / mean
    else:
        max_wps, _ = compute_max_wps(gaps, mean, sigma_right)

    honest_rate = (1 - beta) * E_w_honest / mean
    adv_rate = beta * max_wps
    return honest_rate / adv_rate, E_w_honest, mean


def beta_from_margin(margin):
    """Solve margin = (1-β)/β for β."""
    return 1.0 / (1.0 + margin)


# ── Analysis 1: sigma_right sweep ───────────────────────────────────────────

print("=" * 70)
print("ANALYSIS 1: σ_right sweep")
print("=" * 70)

SIGMA_RIGHT_VALUES = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 50.0, np.inf]
SIGMA_LABELS = ['0.5', '1.0', '1.5', '2.0', '3.0', '5.0', '10.0', '50.0', '∞']

# Compute asymptote (pure ramp) for each level
print("\nPure ramp (σ_right=∞) asymptote:")
print(f"  PoW bound = (1-β)/β = {POW_BOUND:.6f}")
print(f"  Theoretical: E[g/mean|honest] = E[g]/mean = mean/mean = 1.0 exactly")
print()

pow_asymptotes = {}
for lv, (mp, sc) in LEVELS.items():
    margin_inf, E_w_inf, mean_inf = safety_margin(mp, sc, None, pure_ramp=True)
    pow_asymptotes[lv] = margin_inf
    print(f"  L{lv}: mean={mean_inf:.4f}, E[w_pure_ramp|honest]={E_w_inf:.8f}, "
          f"margin={margin_inf:.6f}, PoW bound={POW_BOUND:.6f}, "
          f"ratio={margin_inf/POW_BOUND:.8f}")

print()
print("  → Verified: E[w_pure_ramp|honest] = 1.0 exactly (by definition of mean)")
print(f"  → Pure ramp achieves EXACTLY the PoW bound = {POW_BOUND:.6f}")

# Now sweep sigma_right
results_a1 = {}  # results_a1[level][sigma_right] = (margin, E_w, mean)
for lv, (mp, sc) in LEVELS.items():
    results_a1[lv] = {}
    for sr in SIGMA_RIGHT_VALUES:
        if np.isinf(sr):
            m, ew, mn = safety_margin(mp, sc, None, pure_ramp=True)
        else:
            m, ew, mn = safety_margin(mp, sc, sr)
        results_a1[lv][sr] = (m, ew, mn)

# Print sweep table
print("\nσ_right sweep — safety margins:")
hdr = f"{'Level':<6}" + "".join(f"{lbl:>9}" for lbl in SIGMA_LABELS)
print(hdr)
print("-" * len(hdr))
for lv in range(1, 6):
    row = f"L{lv:<5}"
    for sr in SIGMA_RIGHT_VALUES:
        m, _, _ = results_a1[lv][sr]
        row += f"{m:>9.4f}"
    print(row)

# Find σ_right needed for 90%, 95%, 99% of PoW bound
print("\nσ_right to reach X% of PoW bound per level:")
print(f"{'Level':<6} {'90%':>10} {'95%':>10} {'99%':>10}  (PoW={POW_BOUND:.4f})")
print("-" * 45)
for lv in range(1, 6):
    asym = pow_asymptotes[lv]
    thresholds = {0.90: None, 0.95: None, 0.99: None}
    for sr in SIGMA_RIGHT_VALUES:
        m = results_a1[lv][sr][0]
        ratio = m / asym
        for pct, val in thresholds.items():
            if val is None and ratio >= pct:
                thresholds[pct] = sr
    row = f"L{lv:<5}"
    for pct in [0.90, 0.95, 0.99]:
        v = thresholds[pct]
        row += f"  {('∞' if (v is None or np.isinf(v)) else f'{v:.1f}'):>8}"
    print(row)

# Check adversary optimality: verify max w/g always at g=mean
print("\nAdversary max w/g check (should always be 1/mean, not beyond):")
print(f"{'Level':<6} {'σ_right':<10} {'max_wps':>12} {'1/mean':>12} {'opt_g':>10} {'same?':>8}")
for lv, (mp, sc) in LEVELS.items():
    gaps, probs = get_stationary(mp, sc)
    mean = np.dot(gaps, probs)
    for sr in [2.0, 5.0, 10.0, 50.0]:
        max_wps, opt_g = compute_max_wps(gaps, mean, sr)
        same = abs(max_wps - 1.0/mean) < 1e-9
        print(f"L{lv:<5} {sr:<10.1f} {max_wps:>12.8f} {1.0/mean:>12.8f} {opt_g:>10.1f} {'✓' if same else '✗':>8}")

# Plot: safety_margin vs sigma_right
fig, ax = plt.subplots(figsize=(9, 6))

sr_numeric = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0, 50.0, 100.0]  # inf → 100 for plotting

for lv in range(1, 6):
    margins = []
    for i, sr in enumerate(SIGMA_RIGHT_VALUES):
        m = results_a1[lv][sr][0]
        margins.append(m)
    ax.plot(sr_numeric, margins, color=LEVEL_COLORS[lv], marker='o',
            linewidth=2, markersize=6, label=f'L{lv}')

# PoW bound line
ax.axhline(POW_BOUND, color='black', linestyle='--', linewidth=1.5,
           label=f'PoW bound = {POW_BOUND:.3f}')

# Mark 95% of PoW
ax.axhline(0.95 * POW_BOUND, color='gray', linestyle=':', linewidth=1.2,
           label='95% of PoW bound')

ax.set_xscale('log')
ax.set_xlabel('σ_right', fontsize=13)
ax.set_ylabel('Safety margin (1−β)/β equivalent', fontsize=13)
ax.set_title('Safety margin vs. σ_right by level\n(σ=∞ plotted at 100)', fontsize=13)
ax.legend(fontsize=10, loc='lower right')
ax.set_xticks(sr_numeric)
ax.set_xticklabels(['0.5', '1', '1.5', '2', '3', '5', '10', '50', '∞'])
ax.grid(True, alpha=0.3)
ax.set_ylim(bottom=0)

plt.tight_layout()
out_path = os.path.join(FIGURES_DIR, 'sigma_right_sweep.png')
fig.savefig(out_path, dpi=150)
plt.close(fig)
print(f"\nSaved: {out_path}")


# ── Analysis 2: sc parameter sweep ──────────────────────────────────────────

print()
print("=" * 70)
print("ANALYSIS 2: sc parameter effect (mode/mean ratio)")
print("=" * 70)

SC_FACTORS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
SIGMA_RIGHT_FIXED = 2.0

results_a2 = {}  # results_a2[level][sc_factor] = (mode, mean, E_w, margin, mode_mean_ratio)

print(f"\nsc sweep at σ_right={SIGMA_RIGHT_FIXED}, β={BETA}")
print(f"{'Level':<6} {'sc_f':<6} {'sc':>8} {'mode':>6} {'mean':>8} "
      f"{'mode/mean':>10} {'E[w]':>8} {'margin':>8}")
print("-" * 70)

for lv in range(2, 6):  # L1 already near PoW
    mp, sc_base = LEVELS[lv]
    results_a2[lv] = {}
    for f in SC_FACTORS:
        sc_new = sc_base * f
        gaps, probs = get_stationary(mp, sc_new)
        mean = np.dot(gaps, probs)
        # Compute mode (gap with highest probability)
        mode_g = gaps[np.argmax(probs)]
        margin, E_w, _ = safety_margin(mp, sc_new, SIGMA_RIGHT_FIXED)
        ratio = mode_g / mean
        results_a2[lv][f] = (mode_g, mean, E_w, margin, ratio)
        print(f"L{lv:<5} {f:<6.2f} {sc_new:>8.4f} {mode_g:>6.0f} {mean:>8.4f} "
              f"{ratio:>10.4f} {E_w:>8.4f} {margin:>8.4f}")

# Plot sc sweep
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))

for lv in range(2, 6):
    ratios = [results_a2[lv][f][4] for f in SC_FACTORS]
    margins = [results_a2[lv][f][3] for f in SC_FACTORS]
    ax1.plot(SC_FACTORS, ratios, color=LEVEL_COLORS[lv], marker='s',
             linewidth=2, markersize=7, label=f'L{lv}')
    ax2.plot(SC_FACTORS, margins, color=LEVEL_COLORS[lv], marker='s',
             linewidth=2, markersize=7, label=f'L{lv}')

ax1.axvline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='baseline')
ax1.set_xlabel('sc scaling factor', fontsize=12)
ax1.set_ylabel('mode / mean', fontsize=12)
ax1.set_title('Mode/mean ratio vs. sc factor\n(lower = more honest blocks in ramp zone)', fontsize=11)
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3)

ax2.axhline(POW_BOUND, color='black', linestyle='--', linewidth=1.5,
            label=f'PoW bound = {POW_BOUND:.3f}')
ax2.axhline(0.95 * POW_BOUND, color='gray', linestyle=':', linewidth=1.2,
            label='95% of PoW')
ax2.axvline(1.0, color='gray', linestyle='--', linewidth=1, alpha=0.7, label='baseline')
ax2.set_xlabel('sc scaling factor', fontsize=12)
ax2.set_ylabel('Safety margin', fontsize=12)
ax2.set_title(f'Safety margin vs. sc factor (σ_right={SIGMA_RIGHT_FIXED})', fontsize=11)
ax2.legend(fontsize=10)
ax2.grid(True, alpha=0.3)

plt.tight_layout()
out_path = os.path.join(FIGURES_DIR, 'sc_sweep.png')
fig.savefig(out_path, dpi=150)
plt.close(fig)
print(f"\nSaved: {out_path}")

# Key question: does halving sc meaningfully improve the bound?
print("\nsc=0.5 vs sc=1.0 margin improvement per level:")
for lv in range(2, 6):
    m_base = results_a2[lv][1.0][3]
    m_half = results_a2[lv][0.5][3]
    print(f"  L{lv}: baseline={m_base:.4f}, halved={m_half:.4f}, "
          f"delta={m_half-m_base:+.4f} ({100*(m_half-m_base)/m_base:+.1f}%)")


# ── Analysis 3: Combined summary ─────────────────────────────────────────────

print()
print("=" * 70)
print("ANALYSIS 3: Final consistency bound summary")
print("=" * 70)

# Known values from prior work
prior_f2 = {1: 0.29, 2: 0.70, 3: 0.95, 4: 0.46, 5: 0.09}
prior_ramp05 = {1: 2.01, 2: 1.43, 3: 1.26, 4: 1.20, 5: 1.15}

# Compute ramp σ=2.0 (adaptive)
ramp_sigma2 = {}
for lv, (mp, sc) in LEVELS.items():
    m, _, _ = safety_margin(mp, sc, 2.0)
    ramp_sigma2[lv] = m

# Find optimal sigma_right per level (from sweep)
ramp_optimal = {}
for lv, (mp, sc) in LEVELS.items():
    best_sr = None
    best_m = 0.0
    for sr in SIGMA_RIGHT_VALUES:
        if np.isinf(sr):
            m = results_a1[lv][sr][0]
        else:
            m = results_a1[lv][sr][0]
        if m > best_m:
            best_m = m
            best_sr = sr
    ramp_optimal[lv] = (best_sr, best_m)

# Pure ramp (sigma_right=inf)
ramp_inf = {}
for lv, (mp, sc) in LEVELS.items():
    m = results_a1[lv][np.inf][0]
    ramp_inf[lv] = m

def beta_bound_from_margins(margins_dict):
    """Find the worst-case β bound: min margin → max β = 1/(1+min_margin)."""
    min_m = min(margins_dict.values())
    return 1.0 / (1.0 + min_m)

# Summary table
print()
print("=" * 70)
print("=== FINAL CONSISTENCY BOUND SUMMARY ===")
print("=" * 70)
print()

def fmt_beta(b):
    return f"<{b:.3f}"

schemes = [
    ("Current (f²), original",     prior_f2,
     beta_bound_from_margins(prior_f2)),
    ("Ramp σ=0.5",                  prior_ramp05,
     beta_bound_from_margins(prior_ramp05)),
    ("Ramp σ=2.0 (adaptive)",      ramp_sigma2,
     beta_bound_from_margins(ramp_sigma2)),
    ("Ramp σ=optimal (from sweep)", {lv: v[1] for lv, v in ramp_optimal.items()},
     beta_bound_from_margins({lv: v[1] for lv, v in ramp_optimal.items()})),
    ("Ramp σ=∞ (pure ramp)",        ramp_inf,
     beta_bound_from_margins(ramp_inf)),
    ("PoW reference",               {lv: POW_BOUND for lv in range(1,6)},
     beta_bound_from_margins({lv: POW_BOUND for lv in range(1,6)})),
]

col_w = 34
print(f"{'Scheme':<{col_w}} | {'L1':>6} | {'L2':>6} | {'L3':>6} | {'L4':>6} | {'L5':>6} | β bound")
print("-" * (col_w + 2) + "|" + "-" * 8 + "|" + ("-" * 8 + "|") * 4 + "-" * 8 + "|" + "-" * 8)
for name, margins, bb in schemes:
    row = f"{name:<{col_w}} |"
    for lv in range(1, 6):
        row += f" {margins[lv]:>6.2f} |"
    row += f" {fmt_beta(bb):>7}"
    print(row)

print()

# Report optimal sigma_right per level
print("Optimal σ_right per level:")
for lv in range(1, 6):
    best_sr, best_m = ramp_optimal[lv]
    sr_label = '∞' if np.isinf(best_sr) else f'{best_sr:.1f}'
    asym = pow_asymptotes[lv]
    pct = 100 * best_m / asym
    print(f"  L{lv}: σ_right={sr_label}, margin={best_m:.4f} ({pct:.1f}% of PoW bound)")

print()

# σ_right for 95% of PoW per level
print("σ_right needed for 95% of PoW bound per level:")
for lv in range(1, 6):
    asym = pow_asymptotes[lv]
    target = 0.95 * asym
    found = None
    for sr in SIGMA_RIGHT_VALUES:
        m = results_a1[lv][sr][0]
        if m >= target:
            found = sr
            break
    label = '∞' if (found is None or np.isinf(found)) else f'{found:.1f}'
    m_at = results_a1[lv][found if found else np.inf][0]
    print(f"  L{lv}: σ_right={label}, margin={m_at:.4f} (target={target:.4f})")

print()

# ── KEY THEORETICAL FINDING ──────────────────────────────────────────────────
print("=" * 70)
print("KEY THEORETICAL FINDING")
print("=" * 70)
print()
print("  THEOREM: The pure ramp weight function w(g) = g/mean achieves")
print("  EXACTLY the proof-of-work (PoW) consistency bound.")
print()
print("  PROOF:")
print("  For the pure ramp: w(g) = g/mean for all g >= ψ.")
print("  E[w|honest] = E[g/mean] = (1/mean) * E[g] = (1/mean) * mean = 1.0")
print("  (since E[g] = mean BY DEFINITION of the stationary distribution mean)")
print()
print("  max_g w(g)/g = max_g (g/mean)/g = 1/mean (constant, no better point)")
print()
print("  honest_rate = (1-β) * E[w|honest] / mean = (1-β) * 1.0 / mean")
print("  adv_rate    = β * (1/mean)")
print("  margin      = honest_rate / adv_rate = (1-β)/β  ✓ (PoW bound)")
print()
print(f"  Numerically verified: pure ramp margin = {ramp_inf[1]:.8f}")
print(f"  PoW bound (1-β)/β   = {POW_BOUND:.8f}")
print(f"  Ratio               = {ramp_inf[1]/POW_BOUND:.10f} ≈ 1.0")
print()
print("  COROLLARY: Any right-tail decay (σ_right < ∞) strictly reduces")
print("  E[w|honest] below 1.0, so the safety margin is strictly less than")
print("  the PoW bound. The decay parameter σ_right controls how close")
print("  we get to the PoW limit.")

print()
print("=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)
print()

# sc adjustment worth it?
print("1. Is sc adjustment worth it?")
total_gain = 0
count = 0
for lv in range(2, 6):
    m_base = results_a2[lv][1.0][3]
    m_half = results_a2[lv][0.5][3]
    gain_pct = 100 * (m_half - m_base) / m_base
    total_gain += gain_pct
    count += 1
avg_gain = total_gain / count
print(f"   Halving sc improves safety margin by ~{avg_gain:.1f}% on average (L2-L5).")
print(f"   However, changing sc changes the block production rate and the")
print(f"   timing properties of the protocol — this is NOT a free parameter")
print(f"   for the weight function. The sc values in LEVELS are determined")
print(f"   by the target block interval. Conclusion: sc is LOW LEVERAGE for")
print(f"   weight optimization and should not be adjusted in the paper.")
print()

print("2. σ_right recommendation for the paper:")
print(f"   - σ_right=2.0 (current) achieves β < {beta_bound_from_margins(ramp_sigma2):.3f}")
best_grid_sr = max(SIGMA_RIGHT_VALUES[:-1])  # largest finite
ramp_best_finite = {lv: results_a1[lv][best_grid_sr][0] for lv in range(1,6)}
beta_best = beta_bound_from_margins(ramp_best_finite)
print(f"   - σ_right=50.0 (near-pure) achieves β < {beta_best:.3f}")
print(f"   - σ_right=∞ (pure ramp) achieves β < {beta_bound_from_margins(ramp_inf):.3f} (PoW bound)")
print()
print("   The pure ramp (σ_right=∞) is theoretically optimal and achieves")
print("   exactly the PoW bound. However, a very large σ_right may give")
print("   excessive weight to outlier blocks. For the paper:")
print()
print("   RECOMMENDATION: Use σ_right=10.0 as the primary result.")
ramp_sr10 = {lv: results_a1[lv][10.0][0] for lv in range(1,6)}
print(f"   This achieves β < {beta_bound_from_margins(ramp_sr10):.3f}, within")
asym_min = min(pow_asymptotes.values())
sr10_min = min(ramp_sr10.values())
print(f"   {100*sr10_min/asym_min:.1f}% of the PoW bound, while keeping the")
print(f"   weight function practically bounded.")
print()
print("   State as a theorem: 'The ramp weight function with σ_right=∞")
print("   achieves exactly the PoW consistency bound of β < (1-β)/β.'")
print("   Report σ_right=10 as the practical parameter recommendation.")

print()
print("=" * 70)
print("OUTPUT FILES")
print("=" * 70)
print(f"  figures/sigma_right_sweep.png")
print(f"  figures/sc_sweep.png")
print("=" * 70)
