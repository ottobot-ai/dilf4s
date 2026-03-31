"""
Figure C: LDD Gating Asymmetry Intuition Plot
Shows why the consistency bound improves: the LDD snowplow creates
an asymmetry between honest and adversarial block production.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import os

# ── LDD parameters ──────────────────────────────────────────────────────────
psi   = 0      # dead zone (slots)
gamma = 15     # cutoff
f_A   = 0.5   # max threshold (at gamma)
f_B   = 0.05  # baseline threshold (above gamma)
stake = 0.15  # representative honest stake

def f_ldd(delta):
    """LDD snowplow threshold (probability per slot for given stake)."""
    if np.isscalar(delta):
        if delta < psi:
            return 0.0
        elif delta < gamma:
            return f_A * (delta - psi) / (gamma - psi)
        else:
            return f_B
    else:
        delta = np.asarray(delta, dtype=float)
        result = np.zeros_like(delta)
        mask_ramp = (delta >= psi) & (delta < gamma)
        mask_flat = delta >= gamma
        result[mask_ramp] = f_A * (delta[mask_ramp] - psi) / (gamma - psi)
        result[mask_flat] = f_B
        return result

def eligibility(delta, alpha=stake):
    """Eligibility threshold phi(delta, alpha) = 1 - (1 - f(delta))^alpha."""
    return 1 - (1 - f_ldd(delta)) ** alpha

def gating(delta):
    """Slot-gap gating factor s(delta) = min(1, delta/gamma)."""
    return np.minimum(1.0, np.asarray(delta, dtype=float) / gamma)

# ── Key values ───────────────────────────────────────────────────────────────
mean_gap_honest = 5.2   # stationary distribution mean for honest blocks
delta_adv       = 1     # adversary at Δ=0 boundary

g_honest = gating(mean_gap_honest)
g_adv    = gating(delta_adv)
ratio    = g_honest / g_adv

delta_range = np.linspace(0.01, 30, 500)

# ── Figure ───────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(12, 5))
gs  = GridSpec(1, 2, figure=fig, wspace=0.35)

# ── Left panel: snowplow curve with zones ─────────────────────────────────
ax1 = fig.add_subplot(gs[0])

f_vals = f_ldd(delta_range)
ax1.plot(delta_range, f_vals, 'k-', lw=2.5, zorder=5, label='LDD snowplow $f(\\delta)$')

# Ramp zone shading (0 < δ < γ)
ax1.axvspan(0, gamma, alpha=0.10, color='red',  label='Ramp zone ($\\delta < \\gamma=15$)')
# Recovery zone shading (δ ≥ γ)
ax1.axvspan(gamma, 30, alpha=0.10, color='blue', label='Recovery zone ($\\delta \\geq \\gamma$)')

# Honest mean gap line
ax1.axvline(mean_gap_honest, color='steelblue', lw=2, ls='--', zorder=6)
ax1.annotate(f'Honest blocks\nland here\n($\\bar\\delta \\approx {mean_gap_honest}$)',
             xy=(mean_gap_honest, f_ldd(mean_gap_honest)),
             xytext=(mean_gap_honest + 3, 0.28),
             fontsize=9, color='steelblue',
             arrowprops=dict(arrowstyle='->', color='steelblue', lw=1.5))

# Adversary line
ax1.axvline(delta_adv, color='firebrick', lw=2, ls='--', zorder=6)
ax1.annotate(f'Adversary at\n$\\Delta=0$ lands\nhere ($\\delta={delta_adv}$)',
             xy=(delta_adv, f_ldd(delta_adv)),
             xytext=(delta_adv + 2.5, 0.40),
             fontsize=9, color='firebrick',
             arrowprops=dict(arrowstyle='->', color='firebrick', lw=1.5))

ax1.axvline(gamma, color='gray', lw=1.2, ls=':', alpha=0.8)
ax1.set_xlabel('Slot gap $\\delta$', fontsize=11)
ax1.set_ylabel('LDD threshold $f(\\delta)$', fontsize=11)
ax1.set_title('(a) LDD Snowplow Curve', fontsize=12, fontweight='bold')
ax1.set_xlim(0, 30)
ax1.set_ylim(-0.01, 0.55)
ax1.legend(fontsize=8, loc='upper right')
ax1.grid(True, alpha=0.3)

# ── Right panel: gating factor bar chart ─────────────────────────────────
ax2 = fig.add_subplot(gs[1])

labels  = [f'Adversary\n($\\delta = {delta_adv}$)', f'Honest\n($\\bar\\delta \\approx {mean_gap_honest}$)']
heights = [g_adv, g_honest]
colors  = ['firebrick', 'steelblue']

bars = ax2.bar(labels, heights, color=colors, edgecolor='black', linewidth=1.2, width=0.5)

for bar, h in zip(bars, heights):
    ax2.text(bar.get_x() + bar.get_width() / 2,
             h + 0.005, f'{h:.3f}',
             ha='center', va='bottom', fontsize=11, fontweight='bold')

# Annotate ratio
ax2.annotate('', xy=(1, g_honest), xytext=(1, g_adv),
             arrowprops=dict(arrowstyle='<->', color='black', lw=2))
ax2.text(1.28, (g_honest + g_adv) / 2,
         f'$\\approx {ratio:.1f}\\times$\nasymmetry',
         ha='left', va='center', fontsize=11, color='black', fontweight='bold')

ax2.set_ylabel('Gating factor $s(\\delta) = \\min(1,\\ \\delta/\\gamma)$', fontsize=11)
ax2.set_title('(b) Gating Factor Asymmetry', fontsize=12, fontweight='bold')
ax2.set_ylim(0, 0.45)
ax2.grid(True, axis='y', alpha=0.3)

# Add caption annotation
ax2.text(0.5, -0.18,
         f'$5\\times$ gating asymmetry → $\\sim$20\\% consistency bound improvement',
         transform=ax2.transAxes, ha='center', fontsize=9,
         style='italic', color='darkslategray')

fig.suptitle('LDD Gating Asymmetry: The Source of Consistency Improvement',
             fontsize=13, fontweight='bold', y=1.02)

plt.tight_layout()

# ── Save ─────────────────────────────────────────────────────────────────────
out_dir = os.path.join(os.path.dirname(__file__), 'figures')
os.makedirs(out_dir, exist_ok=True)

png_path = os.path.join(out_dir, 'gating_asymmetry.png')
pdf_path = os.path.join(out_dir, 'gating_asymmetry.pdf')

fig.savefig(png_path, dpi=150, bbox_inches='tight')
fig.savefig(pdf_path, bbox_inches='tight')

print(f"Saved: {png_path}")
print(f"Saved: {pdf_path}")
plt.close(fig)
