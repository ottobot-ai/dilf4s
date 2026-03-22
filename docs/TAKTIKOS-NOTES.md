# Taktikos Protocol — Design Notes & Learnings

**Author:** James + CodeBot  
**Date:** 2026-03-22  
**Paper:** Ouroboros Taktikos (FC 2023), `docs/taktikos-fc2023.pdf`

---

## Core Concepts

### Local Dynamic Difficulty (LDD) — The Snowplow Curve

The threshold function `φ(δ, α)` determines forging eligibility based on the **slot gap** (δ = slots since last block) and **relative stake** (α).

Full form from the paper (Eq. 3):
```
f(δ) = 0                              if δ < ψ       (dormant)
       fA × (δ - ψ) / (γ - ψ)        if ψ ≤ δ < γ   (ramp)
       fB                              if δ ≥ γ        (recovery/baseline)

threshold = 1 - (1 - f(δ))^α
```

Where ψ = offset (psi), γ = cutoff (gamma), fA = amplitude, fB = baseline.

**Three regimes:**
1. **Dormant (δ < ψ):** f=0. No eligibility possible. Accounts for network delay.
2. **Ramp (ψ ≤ δ < γ):** Threshold increases linearly. Low gap = low threshold = HARD to forge.
3. **Recovery (δ ≥ γ):** Drops to baseline. Deliberately throttled to prevent burst.

**Shape:** Dormant → ramp up → cliff down → flat baseline. NOT monotonically increasing.

**Key insight:** Low threshold = high difficulty. Threshold and difficulty are INVERSE.

**Note:** The ramp never reaches full amplitude (strict `δ < γ`). At `δ = γ-1`: `f = fA × (γ-1-ψ)/(γ-ψ)`, then `f(γ) = fB`. Consider making γ inclusive if you want peak to hit fA.

Default params (Bifrost): `ψ=0, γ=50 (lddCutoff), fA=1/2 (amplitude), fB=1/20 (baseline)`

### Eligibility Test

```
rho = VRF_proofToHash(VRF_sign(sk, eta || slot))
testValue = Blake2b512(rho || "TEST") / 2^512    ∈ [0, 1)
eligible = testValue < threshold
```

### Epoch Randomness (Eta)

```
rhoNonceHash = Blake2b512(rho || "NONCE")
nextEta = Blake2b256(previousEta || epoch || concat(rhoNonceHashes))
```

Uses first 2/3 of epoch's rho values to prevent last-slot grinding.

---

## Chain Selection: maxvalid-tk

```
maxvalid-tk(k, C_loc, C_1, ..., C_j):
  C ← C_loc
  for each C_i:
    if valid(C_i) AND fork_depth ≤ k:
      if |C_i| > |C|:                           // Rule 1: longer chain wins
        C ← C_i
      else if |C_i| = |C|:
        if slot(head(C_i)) < slot(head(C)):      // Rule 2: lower head slot wins
          C ← C_i
  return C
```

**Rules in priority order:**
1. Candidate must be valid and fork within k blocks (security parameter, default k=50)
2. **Longer chain wins** (strictly more blocks → adopt)
3. **Equal length → lower head slot wins** (Taktikos-specific, not in Praos)

### Why Lower Head Slot?

Lower head slot is a **proxy for having beaten a harder threshold**. A block forged at a small gap had a low threshold (high difficulty), meaning the staker's VRF output was genuinely strong. This rewards fast honest forging.

### Why NOT Lowest Nonce Tiebreaker?

**Do not** use VRF test value (nonce) as a same-slot tiebreaker:

1. **Pseudo-predictability:** VRF outputs are deterministic from `(sk, eta, slot)`. Every staker can pre-compute their test value for all future slots in the epoch.

2. **Selfish mining incentive:** With nonce certainty, a staker can withhold blocks and release strategically.

3. **Pre-computable = exploitable:** Any tiebreaker deterministic from local state gives strategic information that degrades the security model.

**maxvalid-tk avoids this** by resolving forks through future chain growth — the outcome depends on what happens *after* the fork, which is NOT pre-computable.

### LDD + maxvalid-tk Alignment

- **Snowplow:** Forging fast is hard but possible (low gap = low threshold)
- **maxvalid-tk:** The chain that forged faster wins ties (lower head slot)
- **Together:** Both reward the staker who did the hardest work

---

## NiPoPoW-Style Superblock Levels — Design Exploration

### Goal

Emulate PoW NiPoPoWs in PoS: certain blocks get "lucky" hits at multiple difficulty levels, forming embedded subchains that enable logarithmic light client proofs.

### Block Header Subchain State

Each block header carries a vector of `(lastHitSlot, height, tipHash)` tuples — one per level:

```scala
subchainState: Vector[(Long, Long, Array[Byte])]  // per level: (slot, height, H(this))
```

- When a block hits level μ: `subchainState(μ) = (thisSlot, parentHeight + 1, H(this))`
- When a block misses level μ: `subchainState(μ) = parent.subchainState(μ)` (carried forward)
- Heights enable easy change detection and subchain indexing
- Walking back level-μ superchain: follow tipHash pointers

### Extended maxvalid-tk with Superblock Weight

```
maxvalid-tk-super(k, C_loc, C_1, ..., C_j):
  C ← C_loc
  for each C_i:
    if valid(C_i) AND fork_depth ≤ k:
      if |C_i| > |C|:                              // Rule 1: longer chain
        C ← C_i
      else if |C_i| = |C|:
        if slot(head(C_i)) < slot(head(C)):         // Rule 2: lower head slot
          C ← C_i
        else if slot(head(C_i)) = slot(head(C)):     // Rule 3: richer superblocks
          if superWeight(C_i) > superWeight(C):
            C ← C_i
  return C
```

superWeight: lexicographic comparison of `[h4, h3, h2, h1]` (highest level first).

### Approach 1: Per-Level LDD with ψ Offset (Explored)

Each level has its own snowplow curve with ψ_μ = γ_{μ-1}:

| Level | ψ | γ | Domain |
|-------|---|---|--------|
| L0 | 0 | 15 | "TEST" |
| L1 | 15 | 30 | "TEST-1" |
| L2 | 30 | 60 | "TEST-2" |
| L3 | 60 | 120 | "TEST-3" |
| L4 | 120 | 240 | "TEST-4" |

**Result:** Super levels fire too infrequently when gated behind L0.
The L0 gate limits super levels to ~15% of slots. With ψ offsets further
delaying activation, super levels collapse to baseline rates (~1-4% conditional).

**Key lesson:** Slot-based gaps don't work for super levels gated behind
base eligibility. The gap grows in slots but the test only fires on
~15% of those slots.

### Approach 2: Flat Conditional Probabilities (Explored)

After passing L0, flip a domain-separated coin:
```
P(L1 | L0) = 0.50
P(L2 | L0) = 0.25
P(L3 | L0) = 0.125
P(L4 | L0) = 0.0625
```

**Result:** Rates are correct — 179 → 91 → 51 → 26 → 16 across levels.
Clean ~2x decay. But no snowplow incentive at super levels — stake-blind,
no LDD shaping.

### Approach 3: Deferred Claims (Idea — Not Yet Implemented)

Test all levels every slot independently. When a super-level hits at a
non-block slot, the claim is "deferred" to the next L0 block.

Block at slot 455 claims a deferred L2 hit from slot 450:
```
deferredClaims: [(level=2, claimSlot=450, vrfProof_450)]
```

Verifiable by peers (VRF proof is deterministic). Cost: ~112 bytes per
deferred claim.

**Concern:** Grinding — staker could time L0 blocks to capture deferred
claims. But VRF is deterministic (can't change outcome) and maxvalid-tk
penalizes delayed blocks (lower head slot wins).

### Approach 4: Block-Count Based Gaps (Idea — Under Discussion)

**Key insight:** Use base block count difference instead of slot difference
for super-level gaps. This solves the L0-gating frequency problem.

For levels L1-L3, LDD may not be needed — a fixed conditional probability
based on the block count gap could work:

| Level | Mechanism | Target |
|-------|-----------|--------|
| L0 | LDD snowplow (slot gap) | ~every 7 slots |
| L1 | P ≈ 0.5 per base block | every 2nd block |
| L2 | P ≈ 0.25 per base block | every 4th block |
| L3 | P ≈ 0.125 per base block | every 8th block |
| L4 | LDD snowplow (BLOCK gap) | every 16th block |

L4 gets full LDD treatment but measured in blocks since last L4 hit.
This gives L4 the snowplow's self-regulating properties (opens up when
L4 hasn't hit, throttles when it hits too often) while L1-L3 use
simpler uniform probability.

**Open question:** How to parametrize L1-L9 to reliably signal at the
target rates while still being verifiable and independent?

### Approach 5: Flat Conditional at All Levels (Current Implementation)

P(Lμ|L0) = 1/2^μ for all levels. 10 levels (L0-L9), targeting 1-512 block spacing. 
Confirmed working over 10k slots with clean 2x decay:
  L0=1434, L1=730, L2=351, L3=174, L4=99, L5=48, L6=19, L7=8, L8=6, L9=0

**Problem:** Flat conditional adds zero security beyond base chain length.
An adversary who forges N base blocks automatically gets N/2 L1 hits,
N/4 L2 hits, etc. Superblock weight is deterministic from chain length.
The super levels are cosmetic — they don't increase adversary cost.

### KEY INSIGHT: Per-Level LDD is the Novel Contribution

**Why per-level LDD matters for security (degrees of freedom argument):**

With flat conditional, superblocks are free. With independent LDD curves:
- Each level's threshold depends on when THAT level last hit
- Adversary must simultaneously optimize block timing across all levels
- Domain separation prevents a single lucky VRF from satisfying multiple levels
- A burst of blocks at gap=1 scores zero on every super level (all thresholds ~0)
- Adversary must spread blocks temporally to satisfy multiple snowplows
- Temporal spreading directly limits adversary throughput

This ties superblock security to the TEMPORAL DISTRIBUTION of blocks,
not just block count. That's genuinely novel vs PoW NiPoPoWs.

**Why we haven't solved it yet:**
The engineering challenge is that super levels only get tested on L0 blocks
(~15% of slots), so their gaps measured in slots grow huge and collapse
to baseline. Approaches tried:
1. Slot-based per-level gaps → all collapse to baseline
2. Block-count gaps → inverted rates (higher levels hit more)
3. Extended cutoffs with ψ offsets → still too sparse

**The path forward:**
Each level L0-L9 needs its own independently tuned curve. Not just
scaled versions of L0 — truly different functional forms that account
for:
- Being gated behind L0 (~15% test frequency)
- The gap unit (slots vs blocks vs level-specific measure)
- The desired conditional hit rate given the test frequency
- Interaction between multiple levels' snowplow incentives

This is the paper worth writing — the flat version is a trivial PoW port,
but per-level LDD with properly tuned curves that increase adversary
cost is a genuine contribution to PoS security.

---

## Simulation Notes

Phase 1 results (1000 slots, 5 stakers, 30/25/20/15/10 stake split):
- ~14.5% fill rate (matches f_effective = 15/100)
- ~10-15% of block-producing slots have multi-eligible forks
- Median slot gap: ~6-7 slots
- Stake-proportional block production confirmed
- Recovery phase visible: gaps >15 drop threshold to baseline

---

## Default Protocol Parameters (Bifrost application.conf)

| Parameter | Value | Notes |
|-----------|-------|-------|
| fEffective | 15/100 | Target fill rate |
| vrf-ldd-cutoff (γ) | 50 | Ramp endpoint |
| vrf-precision | 40 | Continued fraction precision |
| vrf-baseline-difficulty (fB) | 1/20 | Recovery phase difficulty |
| vrf-amplitude (fA) | 1/2 | Peak difficulty at cutoff |
| chain-selection-k-lookback | 50 | Security parameter k |
| slot-duration | 1000ms | |
| epochLength | 300 | k * 6 |
| operationalPeriodsPerEpoch | 2 | |

---

## Staker Initialization

```scala
operatorSK = Ed25519.deriveKeyPairFromSeed(blake2b256(seed ++ 0x01))
vrfSK      = Ed25519VRF.deriveKeyPairFromSeed(blake2b256(seed ++ 0x02))
kesSK      = KesProduct.createKeyPair(blake2b256(seed ++ 0x03), height, 0)
```

VRF argument for signing: `eta.data ++ BigInt(slot).toByteArray`
