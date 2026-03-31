"""
challengerModel_ramp.py

Adaptation of consensus_automata/papers/taktikos/challengerModel.py to compare
three chain-selection schemes under a grinding (nothing-at-stake) adversary:

  Scheme A: Static PoS     — flat f(d)=fb, block-count chain selection
  Scheme B: Taktikos LDD   — snowplow f(d), block-count chain selection
  Scheme C: Taktikos + Ramp— snowplow f(d), ramp-weight chain selection

Key metric: Pr[settlement violation at depth k] vs adversary stake fraction.

Structural changes from original challengerModel.py:
  - branches array gains a 5th column: cumulative ramp weight (float)
  - select_branch_weighted() uses weight score instead of block count
  - grinding_sim_scheme() parameterised on (f_fn, weight_fn)
  - __main__ runs all three schemes and overlays prk_data curves
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# ── Reproducibility ────────────────────────────────────────────────────────────
np.random.seed(1)

# ── Protocol parameters (Taktikos snowplow) ────────────────────────────────────
total_slots = 50000
gamma    = 15
slot_gap = 0        # PSI for L0
fa       = 0.5
fb       = 0.05
k_settle = 6
total_forks = 200   # reduced for speed; increase for paper

# ── Ramp weight: w(g) = g / MEAN_GAP  (normalised so E[w|honest]=1) ───────────
def _compute_mean_gap():
    acc, pi_raw = 1.0, []
    for g in range(1, 5000):
        pi_raw.append(acc)
        acc *= (1.0 - f_snow(g))
        if acc < 1e-14:
            break
    pi = np.array(pi_raw)
    pi /= pi.sum()
    return np.dot(np.arange(1, len(pi) + 1), pi)


# ── Difficulty curves ──────────────────────────────────────────────────────────
def f_static(delta):
    """Scheme A: constant baseline — no LDD."""
    return fb


def f_snow(delta):
    """Schemes B/C: Taktikos snowplow."""
    if delta <= slot_gap:
        return 0.0
    elif delta <= gamma:
        return min(1.0, fa * (delta - slot_gap) / (gamma - slot_gap))
    else:
        return fb


MEAN_GAP = _compute_mean_gap()
print(f"Taktikos mean_gap = {MEAN_GAP:.3f}")


def w_count(gap):
    """Plain block count (weight = 1 per block)."""
    return 1.0


def w_ramp(gap):
    """Pure ramp: w(g) = g / mean_gap."""
    return gap / MEAN_GAP


# ── Staking threshold ──────────────────────────────────────────────────────────
def phi(d, a, f_fn):
    return 1.0 - (1.0 - f_fn(d)) ** a


# ── Challenger class (identical to original) ───────────────────────────────────
class Challenger:
    def __init__(self, stake, f_fn):
        self.stake = stake
        self.f_fn  = f_fn
        self.ys    = np.random.rand(total_slots)
        self._cache = {}

    def threshold(self, d):
        if d not in self._cache:
            self._cache[d] = phi(d, self.stake, self.f_fn)
        return self._cache[d]

    def test(self, slot, parent_slot):
        return self.ys[slot % total_slots] < self.threshold(slot - parent_slot)


# ── Branch selection ───────────────────────────────────────────────────────────
def select_branch_count(branches, slot):
    """Original: select max (block_number - reserve), tie-break on oldest parent."""
    best_score = max(b[1] - b[2] for b in branches)
    candidates = [b for b in branches if b[1] - b[2] == best_score]
    return min(candidates, key=lambda b: b[0])


def select_branch_weighted(branches, slot):
    """Ramp: select max (weight_score - adv_weight), tie-break on oldest parent."""
    best_score = max(b[4] - b[3] * w_ramp(1) for b in branches)  # adv penalty
    # Actually: use cumulative weight minus adversary-block mean penalty
    # Simpler: select max total weight (honest weight = weight - adv_contribution)
    # We track: branch[4] = total weight, branch[2] = adv block count
    # Honest weight = branch[4] - adv_blocks * E[w_adv]
    # Since adv blocks arrive at natural gaps too, use branch[3] = adv_weight
    best_w = max(b[4] - b[3] for b in branches)
    candidates = [b for b in branches if b[4] - b[3] == best_w]
    return min(candidates, key=lambda b: b[0])


# ── Core simulation ────────────────────────────────────────────────────────────
def grinding_sim_scheme(num_challenger, num_adversary, f_fn, weight_fn):
    """
    Direct port of challengerModel.grinding_sim with weight function support.

    branches: numpy array, columns [parent_slot, block_number, reserve, margin]
      block_number = total blocks on tine
      reserve      = adversary blocks on tine
      margin       = adv_score - honest_score_gap  (viable when >= 0)

    For block-count scoring:  margin = reserve - (leading_honest - (bn - reserve))
    For weight scoring:       margin = adv_weight - (leading_honest_weight - honest_weight)
                              where honest_weight = total_weight - adv_weight

    We track total_weight and adv_weight in extra columns (4 and 5).
    Pruning: margin > -branch_depth.

    Returns: (effective_growth_rate, fork_interval_list)
    """
    branch_depth = 2
    challengers  = [Challenger(1.0 / num_challenger, f_fn) for _ in range(num_challenger)]

    # cols: [parent_slot, block_number, reserve, margin, total_weight, adv_weight]
    branches = np.zeros((1, 6))

    forked, last_fork = False, 0
    fork_intervals    = []
    slot              = 0

    use_weight = (weight_fn is not w_count)

    while len(fork_intervals) < total_forks:
        new_branches = []

        np.random.shuffle(challengers)
        honest    = challengers[num_adversary:]
        adversary = challengers[:num_adversary]

        # Select best branch for honest party
        if use_weight:
            # Best honest weight = total_w - adv_w
            best_idx = np.argmax(branches[:, 4] - branches[:, 5])
        else:
            # Original: max block_number - reserve, tie-break min parent_slot
            best_score = np.max(branches[:, 1] - branches[:, 2])
            candidates = branches[branches[:, 1] - branches[:, 2] == best_score]
            best_idx   = np.argmin(candidates[:, 0])
            branches_sorted = branches[branches[:, 0].argsort()]
            cand_mask = branches_sorted[:, 1] - branches_sorted[:, 2] == best_score
            honest_branch_row = branches_sorted[cand_mask][0]
            best_idx = np.where((branches == honest_branch_row).all(axis=1))[0][0]

        honest_branch = branches[best_idx]

        for ch in honest:
            if ch.test(slot, int(honest_branch[0])):
                gap = slot - int(honest_branch[0])
                w   = weight_fn(gap)
                new_branches.append([slot,
                                     honest_branch[1]+1,
                                     honest_branch[2],       # reserve unchanged
                                     0,                       # margin computed below
                                     honest_branch[4]+w,
                                     honest_branch[5]])       # adv_weight unchanged

        for branch in branches:
            for ch in adversary:
                if ch.test(slot, int(branch[0])):
                    gap = slot - int(branch[0])
                    w   = weight_fn(gap)
                    new_branches.append([slot,
                                         branch[1]+1,
                                         branch[2]+1,         # +1 adversary block
                                         0,
                                         branch[4]+w,
                                         branch[5]+w])        # +w adversary weight

        if new_branches:
            branches = np.vstack([branches, new_branches])
            branches = np.unique(branches, axis=0)

            if use_weight:
                # Leading honest weight = max(total_w - adv_w) across all branches
                honest_weights = branches[:, 4] - branches[:, 5]
                lead_w = np.max(honest_weights)
                # Margin = how far ahead/behind this branch is in honest weight
                # margin >= 0 means viable
                margins = honest_weights - lead_w  # 0 for best, negative for behind
                # But we want: viable when adv can still catch up
                # Re-use original margin concept: margin = reserve - gap_in_blocks
                leading_honest_block = int(np.max(branches[:, 1] - branches[:, 2]))
                def margin_w(b):
                    hon_w  = b[4] - b[5]          # honest weight on this tine
                    gap_w  = lead_w - hon_w        # how far behind in honest weight
                    adv_w  = b[5]                  # adversary weight on this tine
                    return adv_w - gap_w           # viable when >= 0
                margin_vals = np.array([margin_w(b) for b in branches])
                branches[:, 3] = margin_vals
                branches = branches[margin_vals > -branch_depth]
            else:
                # Original margin logic
                leading_honest_block = int(np.max(branches[:, 1] - branches[:, 2]))
                def add_margin(b):
                    gap     = leading_honest_block - (b[1]-b[2])
                    reserve = b[2]
                    return [b[0], b[1], b[2], reserve - gap, b[4], b[5]]
                branches = np.array([add_margin(b) for b in branches])
                branches = branches[branches[:, 3] > -branch_depth]

            if len(branches) == 0:
                branches = np.zeros((1, 6))
                fork_intervals.append(0)
                forked = False
                slot += 1
                continue

            leading_honest_block = int(np.max(branches[:, 1] - branches[:, 2]))
            num_viable = int(np.sum(branches[:, 3] >= 0))

            if num_viable >= 2:
                if not forked:
                    forked    = True
                    last_fork = leading_honest_block
                elif forked and leading_honest_block - last_fork >= k_settle:
                    forked = False
                    fork_intervals.append(abs(leading_honest_block - last_fork))
            else:
                if forked:
                    forked = False
                    fork_intervals.append(leading_honest_block - last_fork)
                else:
                    fork_intervals.append(0)

            # Limit branch explosion
            if len(branches) > 100:
                branches = branches[branches[:, 3].argsort()][-100:]

        slot += 1

    max_l = int(np.max(branches[:, 1]))
    return max_l / slot, fork_intervals


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    data_points = range(0, 51, 5)   # adversary % from 0 to 50
    adv_axis    = [k / 100 for k in data_points]
    num_challengers = 100

    schemes = [
        ("Static PoS\n(flat f, block count)",  f_static, w_count),
        ("Taktikos LDD\n(plain length)",        f_snow,   w_count),
        ("Taktikos LDD\n+ ramp weight",         f_snow,   w_ramp),
    ]

    all_prk   = {}
    all_chg   = {}

    for scheme_name, f_fn, w_fn in schemes:
        print(f"\n=== {scheme_name.replace(chr(10),' ')} ===", flush=True)
        prk_data = []
        chg_data = []
        for k in data_points:
            print(f"  adv={k}%...", end=' ', flush=True)
            rate, forks = grinding_sim_scheme(num_challengers, k, f_fn, w_fn)
            chg_data.append(rate)
            cnt = sum(1 for f in forks if f >= k_settle)
            p   = cnt / len(forks) if forks else 0.0
            prk_data.append(p)
            print(f"Pr[settle_viol]={p:.4f}", flush=True)
        all_prk[scheme_name] = prk_data
        all_chg[scheme_name] = chg_data

    # ── Plot: Pr[settlement violation] ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 6))
    colors  = ['#e74c3c', '#f39c12', '#27ae60']
    markers = ['o', 's', '^']

    for (scheme_name, *_), color, marker in zip(schemes, colors, markers):
        xs, ys = [], []
        for x, y in zip(adv_axis, all_prk[scheme_name]):
            if y > 0:
                xs.append(x)
                ys.append(np.log10(y))
        ax.scatter(xs, ys, label=scheme_name.replace('\n', ' '),
                   color=color, marker=marker, s=60, zorder=5)

    # Covert adversary reference (PoW bound)
    r_axis = np.linspace(0.01, 0.5, 100)
    covert = np.log10(np.power(2*r_axis, k_settle) * np.power(2-2*r_axis, k_settle))
    ax.plot(r_axis, covert, 'k--', lw=1.5, label=f'Covert (PoW, k={k_settle})', alpha=0.7)

    ax.set_xlabel('Adversary stake fraction', fontsize=13)
    ax.set_ylabel(f'$\\log_{{10}}$ Pr[settlement violation, $k={k_settle}$]', fontsize=12)
    ax.set_title('Settlement Security: Static PoS vs Taktikos LDD vs Taktikos + Ramp Weight\n'
                 '(grinding / nothing-at-stake adversary)', fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout()

    out = Path(__file__).parent / 'figures' / 'challenger_settle_comparison.png'
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f'\nSaved: {out}')

    # ── Plot: effective chain growth ───────────────────────────────────────────
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    for (scheme_name, *_), color in zip(schemes, colors):
        ax2.plot(adv_axis, all_chg[scheme_name],
                 label=scheme_name.replace('\n', ' '), color=color, lw=2, marker='o', ms=5)
    ax2.set_xlabel('Adversary stake fraction', fontsize=13)
    ax2.set_ylabel('Effective chain growth rate (blocks/slot)', fontsize=12)
    ax2.set_title('Chain Growth vs Adversarial Stake', fontsize=12)
    ax2.legend(fontsize=10)
    ax2.grid(alpha=0.3)
    fig2.tight_layout()
    out2 = Path(__file__).parent / 'figures' / 'challenger_growth_comparison.png'
    fig2.savefig(out2, dpi=150)
    print(f'Saved: {out2}')
