"""
Figure D: Weight vs Grinding Intuition
Left: Timeline showing how ramp weight rewards adversary's dormant branches.
Right: Pr[settlement violation] vs adversary stake for three schemes.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import os

# ── Grinding simulation data (hardcoded from simulation output) ──────────────
adv_stake  = [0,  5, 10,   15,   20,   25,   30,   35,   40,   45,   50]
p_static   = [0,  0,  0,    0, 0.01, 0.01, 0.045, 0.23, 0.78, 0.97, 0.945]
p_ldd      = [0,  0,  0, 0.005, 0.015, 0.02, 0.52, 0.955, 0.85, 0.91, 1.0]
p_ramp     = [0,  0, 0.325, 0.335, 0.695, 0.62, 0.855, 0.815, 0.95, 0.925, 0.995]

mean_gap = 5.2   # honest mean slot gap

# ── Figure ───────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(13, 5.5))
gs  = GridSpec(1, 2, figure=fig, wspace=0.38)

# ═══════════════════════════════════════════════════════
# Left panel: Timeline intuition diagram
# ═══════════════════════════════════════════════════════
ax1 = fig.add_subplot(gs[0])
ax1.set_xlim(0, 25)
ax1.set_ylim(-1, 3.5)
ax1.axis('off')
ax1.set_title('(a) Why Ramp Weighting Hurts: Dormant Branch Attack',
              fontsize=11, fontweight='bold', pad=8)

# Slot timeline
t_max = 22
ax1.annotate('', xy=(t_max, 2.2), xytext=(0, 2.2),
             arrowprops=dict(arrowstyle='->', color='gray', lw=1.5))
ax1.text(t_max + 0.2, 2.2, 'slots', fontsize=9, va='center', color='gray')
ax1.text(0, 2.5, 'Time', fontsize=9, color='gray')

# Honest chain blocks
honest_slots = [2, 5, 8, 11, 15, 18]
for s in honest_slots:
    ax1.plot(s, 2.2, 's', color='steelblue', ms=8, zorder=5)
    w = s / mean_gap if s > 0 else 1.0
    ax1.text(s, 2.55, f'w={min(w,3.5):.1f}', fontsize=7, ha='center', color='steelblue')
ax1.text(-0.3, 2.2, 'Honest\nchain', fontsize=9, ha='right', va='center', color='steelblue')

# Adversary's main branch (visits at slots 2 and 22)
adv_visit1 = 2
adv_visit2 = 22
gap_dormant = adv_visit2 - adv_visit1  # = 20 slots
w_dormant   = gap_dormant / mean_gap   # ≈ 3.85

ax1.annotate('', xy=(t_max, 0.7), xytext=(0, 0.7),
             arrowprops=dict(arrowstyle='->', color='salmon', lw=1.5, linestyle='dashed'))
ax1.text(t_max + 0.2, 0.7, 'slots', fontsize=9, va='center', color='salmon')

ax1.plot(adv_visit1, 0.7, 'D', color='firebrick', ms=8, zorder=5)
ax1.text(adv_visit1, 1.1, f'w={adv_visit1/mean_gap:.1f}', fontsize=7, ha='center', color='firebrick')

# Dormant zone shading
ax1.axvspan(adv_visit1, adv_visit2, ymin=0.05, ymax=0.55, alpha=0.12, color='orange')
ax1.annotate('', xy=(adv_visit2 - 0.3, 0.0), xytext=(adv_visit1 + 0.3, 0.0),
             arrowprops=dict(arrowstyle='<->', color='darkorange', lw=2))
ax1.text((adv_visit1 + adv_visit2) / 2, -0.35,
         f'Dormant: {gap_dormant} slots', fontsize=9, ha='center', color='darkorange', fontweight='bold')

ax1.plot(adv_visit2, 0.7, 'D', color='firebrick', ms=8, zorder=5)
ax1.text(adv_visit2, 1.1, f'w={w_dormant:.1f}!', fontsize=8, ha='center',
         color='firebrick', fontweight='bold')

# Arrow highlighting the high weight
ax1.annotate(f'Adversary earns\nw = {gap_dormant}/{mean_gap:.1f} ≈ {w_dormant:.1f}×\nfor "free"!',
             xy=(adv_visit2, 0.7), xytext=(adv_visit2 - 7, -0.8),
             fontsize=9, color='firebrick', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color='firebrick', lw=1.5))

ax1.text(-0.3, 0.7, 'Adversary\nbranch', fontsize=9, ha='right', va='center', color='firebrick')

ax1.text(12, 3.1,
         'LDD gating governs WHO gets to produce;\n'
         'ramp weight rewards HOW LONG since last visit.\n'
         'These are orthogonal — and the latter helps the adversary.',
         fontsize=8.5, ha='center', va='center', color='darkslategray',
         bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.8, edgecolor='goldenrod'))

# ═══════════════════════════════════════════════════════
# Right panel: Settlement violation probability
# ═══════════════════════════════════════════════════════
ax2 = fig.add_subplot(gs[1])

ax2.plot(adv_stake, p_static, 'o-', color='steelblue',  lw=2, ms=7,
         label='Static PoS (flat $f$, block count)', zorder=5)
ax2.plot(adv_stake, p_ldd,    's-', color='darkorange', lw=2, ms=7,
         label='Taktikos LDD (plain length)', zorder=5)
ax2.plot(adv_stake, p_ramp,   '^-', color='firebrick',  lw=2, ms=7,
         label='Taktikos LDD + ramp weight', zorder=5)

# Collapse threshold lines
for frac, color, label, yoff in [
    (35, 'steelblue',  'Static PoS collapses\n$\\approx$35%', 0.15),
    (30, 'darkorange', 'LDD plain collapses\n$\\approx$30%', 0.35),
    (10, 'firebrick',  'LDD+ramp collapses\n$\\approx$10%', 0.55),
]:
    ax2.axvline(frac, color=color, lw=1.2, ls=':', alpha=0.7)
    ax2.text(frac + 0.5, yoff, label, color=color, fontsize=7.5, va='bottom')

ax2.axhline(0.5, color='gray', lw=1, ls='--', alpha=0.5, label='50% violation threshold')

ax2.set_xlabel('Adversary stake fraction (%)', fontsize=11)
ax2.set_ylabel('Pr[settlement violation]', fontsize=11)
ax2.set_title('(b) Settlement Security vs.\ Adversary Stake\n(200-fork grinding simulation)',
              fontsize=11, fontweight='bold')
ax2.set_xlim(-1, 52)
ax2.set_ylim(-0.05, 1.10)
ax2.legend(fontsize=8.5, loc='upper left')
ax2.grid(True, alpha=0.3)

# Summary annotation
ax2.text(0.97, 0.12,
         'Ramp weighting is\ncounterproductive\nagainst grinding',
         transform=ax2.transAxes, ha='right', va='bottom',
         fontsize=9, color='firebrick', style='italic',
         bbox=dict(boxstyle='round', facecolor='mistyrose', alpha=0.7, edgecolor='firebrick'))

fig.suptitle('Weighting and Grinding Resistance',
             fontsize=13, fontweight='bold', y=1.02)

plt.tight_layout()

# ── Save ─────────────────────────────────────────────────────────────────────
out_dir = os.path.join(os.path.dirname(__file__), 'figures')
os.makedirs(out_dir, exist_ok=True)

png_path = os.path.join(out_dir, 'weight_grinding_intuition.png')
pdf_path = os.path.join(out_dir, 'weight_grinding_intuition.pdf')

fig.savefig(png_path, dpi=150, bbox_inches='tight')
fig.savefig(pdf_path, bbox_inches='tight')

print(f"Saved: {png_path}")
print(f"Saved: {pdf_path}")
plt.close(fig)
