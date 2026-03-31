"""
Figure D: Weight vs Grinding Intuition  (revised with CI bands)
Left:  Clean timeline – dormant branch attack intuition.
Right: Pr[settlement violation] vs adversary stake, with 95% CI shading.
"""

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os

# ── Load CI data ─────────────────────────────────────────────────────────────
_ci_path = os.path.join(os.path.dirname(__file__), 'grinding_results_ci.json')
with open(_ci_path) as _f:
    _ci = json.load(_f)

stakes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

def _extract(scheme_key):
    d = _ci[scheme_key]
    means = [d[str(s)]["mean"] for s in stakes]
    ci95  = [d[str(s)]["ci95"] for s in stakes]
    return np.array(means), np.array(ci95)

mean_A, ci_A = _extract("A")
mean_B, ci_B = _extract("B")
mean_C, ci_C = _extract("C")

mean_gap = 5.201   # from simulation output

# ── Figure layout ─────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(13, 5.5))
gs  = GridSpec(1, 2, figure=fig, wspace=0.38)

# ═══════════════════════════════════════════════════════════════════════════════
# Panel (a): Clean timeline – dormant branch attack intuition
# ═══════════════════════════════════════════════════════════════════════════════
ax1 = fig.add_subplot(gs[0])
ax1.set_xlim(-1.5, 24)
ax1.set_ylim(-1.6, 3.2)
ax1.axis('off')
ax1.set_title('(a) Dormant Branch Attack: Why Ramp Weight Backfires',
              fontsize=11, fontweight='bold', pad=8)

Y_HON = 1.8   # y-position of honest chain
Y_ADV = 0.3   # y-position of adversary chain

# ── Slot timelines ────────────────────────────────────────────────────────────
t_max = 22
ax1.annotate('', xy=(t_max + 0.5, Y_HON), xytext=(-0.5, Y_HON),
             arrowprops=dict(arrowstyle='->', color='gray', lw=1.2))
ax1.annotate('', xy=(t_max + 0.5, Y_ADV), xytext=(-0.5, Y_ADV),
             arrowprops=dict(arrowstyle='->', color='gray', lw=1.2, linestyle='dashed'))

# ── Honest chain ─────────────────────────────────────────────────────────────
honest_slots = [3, 6, 9, 12, 15, 18]
for s in honest_slots:
    ax1.plot(s, Y_HON, 's', color='steelblue', ms=9, zorder=5)
    ax1.text(s, Y_HON + 0.35, r'$w{\approx}1$', fontsize=7.5,
             ha='center', va='bottom', color='steelblue')

ax1.text(-1.3, Y_HON, 'Honest', fontsize=9.5, ha='right', va='center',
         color='steelblue', fontweight='bold')

# ── Adversary chain: two blocks with big dormant gap ─────────────────────────
adv1 = 3
adv2 = 21   # 20-slot gap → w = 20/5.201 ≈ 3.85 ≈ 3.8
w_adv2 = (adv2 - adv1) / mean_gap  # ≈ 3.84

ax1.plot(adv1, Y_ADV, 'D', color='firebrick', ms=10, zorder=5)
ax1.text(adv1, Y_ADV - 0.45, f'$w=0.6$', fontsize=7.5,
         ha='center', va='top', color='firebrick')

ax1.plot(adv2, Y_ADV, 'D', color='firebrick', ms=10, zorder=5)

# Label near second block
ax1.text(adv2 + 0.6, Y_ADV + 0.45,
         f'20 slot gap $\\rightarrow$ $w={w_adv2:.1f}$',
         fontsize=9, color='firebrick', fontweight='bold', va='bottom', ha='left')

ax1.text(-1.3, Y_ADV, 'Adversary', fontsize=9.5, ha='right', va='center',
         color='firebrick', fontweight='bold')

# ── Double-headed arrow for dormant gap ──────────────────────────────────────
gap_y = Y_ADV - 0.85
ax1.annotate('', xy=(adv2 - 0.2, gap_y), xytext=(adv1 + 0.2, gap_y),
             arrowprops=dict(arrowstyle='<->', color='darkorange', lw=2.2))
ax1.text((adv1 + adv2) / 2, gap_y - 0.35,
         'Dormant: 20 slots', fontsize=9, ha='center', va='top',
         color='darkorange', fontweight='bold')

# ═══════════════════════════════════════════════════════════════════════════════
# Panel (b): Settlement violation probability with CI bands
# ═══════════════════════════════════════════════════════════════════════════════
ax2 = fig.add_subplot(gs[1])

colors  = ['steelblue', 'darkorange', 'firebrick']
markers = ['o',          's',           '^']
labels  = [
    'Static PoS (flat $f$, block count)',
    'Taktikos LDD (plain length)',
    'Taktikos LDD + ramp weight',
]

for mean, ci, color, marker, label in zip(
        [mean_A, mean_B, mean_C],
        [ci_A,   ci_B,   ci_C],
        colors, markers, labels):
    ax2.plot(stakes, mean, f'{marker}-', color=color, lw=2, ms=7,
             label=label, zorder=5)
    ax2.fill_between(stakes, mean - ci, mean + ci,
                     color=color, alpha=0.15, zorder=3)

ax2.axhline(0.5, color='gray', lw=1, ls='--', alpha=0.5,
            label='50% violation threshold')

ax2.set_xlabel('Adversary stake fraction (%)', fontsize=11)
ax2.set_ylabel('Pr[settlement violation]', fontsize=11)
ax2.set_title(r'(b) Settlement Security vs.\ Adversary Stake' + '\n'
              '(50-fork grinding sim, $N=20$ trials, shading = 95% CI)',
              fontsize=10.5, fontweight='bold')
ax2.set_xlim(-1, 52)
ax2.set_ylim(-0.05, 1.10)
ax2.legend(fontsize=8.5, loc='upper left')
ax2.grid(True, alpha=0.3)

fig.suptitle('Weighting and Grinding Resistance',
             fontsize=13, fontweight='bold', y=1.01)

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
