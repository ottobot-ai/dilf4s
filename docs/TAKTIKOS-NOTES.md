# Taktikos Protocol — Design Notes & Learnings

**Author:** James + CodeBot  
**Date:** 2026-03-22  
**Paper:** Ouroboros Taktikos (FC 2023), `docs/taktikos-fc2023.pdf`

---

## Core Concepts

### Local Dynamic Difficulty (LDD) — The Snowplow Curve

The threshold function `φ(δ, α)` determines forging eligibility based on the **slot gap** (δ = slots since last block) and **relative stake** (α).

```
difficulty(δ):
  if δ < γ (lddCutoff):   f(δ) = (amplitude / γ) × δ     — linear ramp
  if δ ≥ γ:               f(δ) = baselineDifficulty        — recovery phase

threshold = 1 - (1 - difficulty)^α
```

**Three regimes:**
1. **Ramp (δ < γ):** Threshold increases linearly. Low gap = low threshold = HARD to forge. High gap approaching cutoff = easier.
2. **At cutoff (δ = γ):** Peak difficulty (amplitude, default 0.5). Easiest point to forge.
3. **Recovery (δ > γ):** Drops to baseline (default 1/20). Deliberately throttled — prevents burst of simultaneous blocks when network recovers.

**Shape:** Ramp up → cliff down → flat baseline. NOT monotonically increasing.

**Key insight:** Low threshold = high difficulty. Threshold and difficulty are INVERSE.

Default params (Bifrost): `γ=15 (lddCutoff=50 in app.conf), amplitude=1/2, baseline=1/20`

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
      if |C_i| > |C|:                           // longer chain wins
        C ← C_i
      else if |C_i| = |C|:                      // equal length:
        if slot(head(C_i)) < slot(head(C)):      //   lower head slot wins
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

**Do not** use VRF test value (nonce) as a same-slot tiebreaker. This is the intuitive-but-wrong approach:

1. **Pseudo-predictability:** VRF outputs are deterministic from `(sk, eta, slot)`. Every staker can pre-compute their test value for all future slots in the epoch. If "lowest nonce wins," a staker knows before forging whether they'd win a conflict.

2. **Selfish mining incentive:** With nonce certainty, a staker can withhold blocks and release strategically — e.g., wait to see if they also win the next slot, building a private longer chain with reduced risk.

3. **Pre-computable = exploitable:** Any tiebreaker that's deterministic from local state gives strategic information that degrades the security model.

**maxvalid-tk avoids this** by resolving forks through chain growth — the outcome depends on what happens *after* the fork (who builds the next block, propagation timing), which is NOT pre-computable. The tiebreaker is emergent from system liveness, not from a deterministic value in the block.

### LDD + maxvalid-tk Alignment

The snowplow curve and maxvalid-tk reinforce each other:
- **Snowplow:** Forging fast is hard but possible (low gap = low threshold)
- **maxvalid-tk:** The chain that forged faster wins ties (lower head slot)
- **Together:** Both reward the staker who did the hardest work — the one who beat a tight threshold quickly

A nonce-based tiebreaker would break this alignment by shifting the incentive from "forge fast" to "forge when your nonce is good."

### Fork Resolution in Practice

When stakers A and B both forge at slot 201:
- Neither chain is longer — tie
- Fork resolves at the **next** block (e.g., staker C at slot 209)
- If C extends A's chain → A's fork has length N+2 vs B's at N+1 → Rule 2 picks A
- If both forks get extended to same length → Rule 3 (lower head slot) breaks it
- This depends on network propagation and timing, not pre-computable values

### Grinding Adversary (Paper Section 4)

The adversary's advantage is bounded precisely because maxvalid-tk doesn't leak exploitable information about who "should" win. The filtration depth `d` (how many slots of rho contribute to next eta) controls grinding power — advantage asymptotes quickly.

---

## Staker Initialization

```scala
operatorSK = Ed25519.deriveKeyPairFromSeed(blake2b256(seed ++ 0x01))
vrfSK      = Ed25519VRF.deriveKeyPairFromSeed(blake2b256(seed ++ 0x02))
kesSK      = KesProduct.createKeyPair(blake2b256(seed ++ 0x03), height, 0)
```

VRF argument for signing: `eta.data ++ BigInt(slot).toByteArray`

---

## Simulation Notes

Phase 1 results (1000 slots, 5 stakers, 30/25/20/15/10 stake split):
- ~14.5% fill rate (matches f_effective = 15/100)
- ~15% of block-producing slots have multi-eligible forks
- Median slot gap: ~7 slots
- Stake-proportional block production confirmed
- Recovery phase visible: gaps >15 drop threshold to baseline, causing extended droughts (48 slots observed)
- Epoch eta rotation every 100 slots

---

## Default Protocol Parameters (Bifrost application.conf)

| Parameter | Value | Notes |
|-----------|-------|-------|
| fEffective | 15/100 | Target fill rate |
| vrf-ldd-cutoff | 50 | γ in paper (slots) |
| vrf-precision | 40 | Continued fraction precision |
| vrf-baseline-difficulty | 1/20 | Recovery phase difficulty |
| vrf-amplitude | 1/2 | Peak difficulty at cutoff |
| chain-selection-k-lookback | 50 | Security parameter k |
| slot-duration | 1000ms | |
| epochLength | 300 | k * 6 |
| operationalPeriodsPerEpoch | 2 | |
