"""Updated figure: clean panel (a) + error bars in panel (b)."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import json, os

# Load CI data
data_path = os.path.join(os.path.dirname(__file__), 'grinding_results_ci.json')
with open(data_path) as f:
    raw = json.load(f)

# Normalise to common format regardless of which subagent wrote the file
def extract(key):
    d = raw[key]
    stakes = sorted(int(k) for k in d.keys() if k != '_meta')
    means = [d[str(s)]['mean'] for s in stakes]
    cis   = [d[str(s)]['ci95'] for s in stakes]
    return stakes, means, cis

stake_A, mean_A, ci_A = extract('A')
stake_B, mean_B, ci_B = extract('B')
stake_C, mean_C, ci_C = extract('C')

mean_gap = 5.2

fig = plt.figure(figsize=(13, 5.5))
gs  = GridSpec(1, 2, figure=fig, wspace=0.40)

# ═══════════════════════════════════════════════════════
# Panel (a): Clean timeline diagram
# ═══════════════════════════════════════════════════════
ax1 = fig.add_subplot(gs[0])
ax1.set_xlim(-2, 24)
ax1.set_ylim(-2.4, 3.2)
ax1.axis('off')
ax1.set_title('(a) Dormant Branch Attack: Ramp Weight Rewards Inactivity',
              fontsize=10.5, fontweight='bold', pad=8)

# Honest chain
ax1.annotate('', xy=(22.5, 1.8), xytext=(0, 1.8),
             arrowprops=dict(arrowstyle='->', color='#aaa', lw=1.5))
honest_slots = [2, 5, 8, 11, 14, 17]
for s in honest_slots:
    ax1.plot(s, 1.8, 's', color='steelblue', ms=9, zorder=5)
    ax1.text(s, 2.22, r'$w{\approx}1$', fontsize=7.5, ha='center', color='steelblue')
ax1.text(-0.3, 1.8, 'Honest', fontsize=9.5, ha='right', va='center',
         color='steelblue', fontweight='bold')

# Adversary chain
ax1.annotate('', xy=(22.5, 0.0), xytext=(0, 0.0),
             arrowprops=dict(arrowstyle='->', color='#aaa', lw=1.5, linestyle='dashed'))
s1, s2 = 2, 21
dormant = s2 - s1
w2 = dormant / mean_gap

ax1.plot(s1, 0.0, 'D', color='firebrick', ms=9, zorder=5)
ax1.text(s1, 0.42, f'$w={s1/mean_gap:.1f}$', fontsize=7.5, ha='center', color='firebrick')

ax1.plot(s2, 0.0, 'D', color='firebrick', ms=9, zorder=5)
ax1.text(s2 + 0.3, 0.42, f'$w={w2:.1f}$', fontsize=9.5, ha='left',
         color='firebrick', fontweight='bold')

# Dormant gap double arrow
ax1.annotate('', xy=(s2 - 0.3, -0.95), xytext=(s1 + 0.3, -0.95),
             arrowprops=dict(arrowstyle='<->', color='darkorange', lw=2.0))
ax1.text((s1 + s2) / 2, -1.45, f'Dormant: {dormant} slots',
         fontsize=9, ha='center', color='darkorange', fontweight='bold')

# "Free weight" callout
ax1.annotate(f'Free weight!\n{dormant}/{mean_gap:.1f} ≈ {w2:.1f}×',
             xy=(s2, 0.18), xytext=(s2 - 6.5, 1.15),
             fontsize=8.5, color='firebrick', fontweight='bold',
             arrowprops=dict(arrowstyle='->', color='firebrick', lw=1.5),
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff0f0',
                       edgecolor='firebrick', alpha=0.9))

ax1.text(-0.3, 0.0, 'Adversary', fontsize=9.5, ha='right', va='center',
         color='firebrick', fontweight='bold')

# Key insight box
ax1.text(11, -2.15,
         'LDD gating controls who can produce blocks.\n'
         'Ramp weight rewards how long since last visit — orthogonal, and exploitable.',
         fontsize=8.5, ha='center', va='center', color='#2d2d2d',
         bbox=dict(boxstyle='round,pad=0.45', facecolor='#fffff0',
                   alpha=0.85, edgecolor='#c8b400'))

# ═══════════════════════════════════════════════════════
# Panel (b): Settlement violation with 95% CI bands
# ═══════════════════════════════════════════════════════
ax2 = fig.add_subplot(gs[1])

schemes = [
    (stake_A, mean_A, ci_A, 'steelblue',  'o', 'Static PoS (flat $f$, block count)'),
    (stake_B, mean_B, ci_B, 'darkorange', 's', 'Taktikos LDD (plain length)'),
    (stake_C, mean_C, ci_C, 'firebrick',  '^', 'Taktikos LDD + ramp weight'),
]

for stakes, means, cis, color, marker, label in schemes:
    m  = np.array(means)
    ci = np.array(cis)
    ax2.plot(stakes, m, marker + '-', color=color, lw=2, ms=7, label=label, zorder=5)
    ax2.fill_between(stakes, np.clip(m - ci, 0, 1), np.clip(m + ci, 0, 1),
                     color=color, alpha=0.15, zorder=3)

ax2.axhline(0.5, color='gray', lw=1, ls='--', alpha=0.5, label='50% threshold')

ax2.set_xlabel('Adversary stake fraction (%)', fontsize=11)
ax2.set_ylabel('Pr[settlement violation] (mean ± 95% CI)', fontsize=10)
ax2.set_title('(b) Settlement Security vs.\ Adversary Stake\n'
              '(grinding simulation, 20 trials per point)',
              fontsize=10.5, fontweight='bold')
ax2.set_xlim(-1, 52)
ax2.set_ylim(-0.05, 1.10)
ax2.legend(fontsize=8.5, loc='upper left')
ax2.grid(True, alpha=0.3)

ax2.text(0.97, 0.12,
         'Ramp weighting is\ncounterproductive\nagainst grinding',
         transform=ax2.transAxes, ha='right', va='bottom',
         fontsize=9, color='firebrick', style='italic',
         bbox=dict(boxstyle='round', facecolor='mistyrose',
                   alpha=0.7, edgecolor='firebrick'))

fig.suptitle('Weighting and Grinding Resistance', fontsize=13, fontweight='bold', y=1.02)
plt.tight_layout()

out_dir = os.path.join(os.path.dirname(__file__), 'figures')
os.makedirs(out_dir, exist_ok=True)
for ext in ('png', 'pdf'):
    path = os.path.join(out_dir, f'weight_grinding_intuition.{ext}')
    kw = {'dpi': 150} if ext == 'png' else {}
    fig.savefig(path, bbox_inches='tight', **kw)
    print(f'Saved {path}')
plt.close(fig)
