package xyz.kd5ujc.taktikos

/**
 * Taktikos leader election types, configuration, and NiPoPoW-style
 * multi-level superblock tracking.
 */

/** Epoch randomness - 32 bytes from Blake2b-256 */
case class Eta(bytes: Array[Byte]) {
  require(bytes.length == 32, s"Eta must be 32 bytes, got ${bytes.length}")
}

/** VRF output hash - 64 bytes from proofToHash */
case class Rho(bytes: Array[Byte]) {
  require(bytes.length == 64, s"Rho must be 64 bytes, got ${bytes.length}")
}

/** A participant in the consensus with VRF keys and stake */
case class Staker(
  id:    Int,
  vrfSK: Array[Byte], // 32 bytes, Ed25519VRF secret key (seed)
  vrfVK: Array[Byte], // 32 bytes, Ed25519VRF verification key
  stake: Long         // absolute stake amount
)

/** Rational number for precise difficulty calculation */
case class Ratio(numerator: BigInt, denominator: BigInt) {
  require(denominator != 0, "Denominator cannot be zero")

  def toDouble: Double = numerator.toDouble / denominator.toDouble

  def *(that: Ratio): Ratio =
    Ratio(this.numerator * that.numerator, this.denominator * that.denominator)

  def /(that: Ratio): Ratio =
    Ratio(this.numerator * that.denominator, this.denominator * that.numerator)

  override def toString: String = s"$numerator/$denominator"
}

object Ratio {
  def apply(n: Int, d: Int): Ratio = Ratio(BigInt(n), BigInt(d))
}

/**
 * VRF configuration for a single level's LDD curve.
 *
 * The full snowplow form from the Taktikos paper:
 *   f(δ) = 0                                  if δ < ψ
 *          fA × (δ - ψ) / (γ - ψ)            if ψ ≤ δ < γ
 *          fB                                  if δ ≥ γ
 *
 * where ψ = offset (psi), γ = lddCutoff (gamma), fA = amplitude, fB = baseline.
 */
case class VrfConfig(
  lddCutoff:          Int,   // γ: cutoff where ramp reaches amplitude (slots)
  offset:             Int,   // ψ: gap below which difficulty is zero (slots)
  precision:          Int,   // Precision for calculations
  baselineDifficulty: Ratio, // fB: difficulty when slotDiff ≥ γ
  amplitude:          Ratio  // fA: peak difficulty at the cutoff
)

// ---------------------------------------------------------------------------
// NiPoPoW-style superblock levels with per-level LDD
// ---------------------------------------------------------------------------

/**
 * Shifted exponential configuration for super levels L1-L9.
 *
 * threshold(gap) = maxProb × (1 - exp(-(gap - psi) / scale))  if gap >= psi
 *                = 0                                          if gap < psi
 *
 * Where gap = base blocks (L0) since this level last hit.
 *
 * Properties:
 * - psi=1 gives burst resistance: threshold=0 at gap=1
 * - Exponential form is smooth and monotonically increasing
 * - maxProb is the asymptotic threshold as gap → ∞
 * - scale controls how fast the curve rises
 */
case class ShiftedExpConfig(
  level:   Int,
  psi:     Int,    // Dormant period (burst resistance)
  maxProb: Double, // Asymptotic probability
  scale:   Double  // Controls rise steepness
) {
  /** Calculate threshold for a given base-block gap. */
  def threshold(gap: Long): Double =
    if (gap < psi) 0.0
    else maxProb * (1.0 - math.exp(-(gap - psi).toDouble / scale))
}

object SuperLevels {
  /**
   * Superblock levels: L0 (base) through L9.
   *
   * L0:    LDD snowplow on SLOT gap (primary chain growth, ~14% fill rate)
   * L1-L9: Shifted exponential on BASE-BLOCK gap (genuine difficulty shaping)
   *
   * Key insight: super levels measure gaps in L0 blocks, not slots or parent-level
   * blocks. This solves the L0-gating frequency problem while maintaining the
   * target 2x decay between levels.
   */
  val Count: Int = 10

  /** Domain separation strings for each level */
  val Domains: Vector[String] = (0 until Count).toVector.map {
    case 0 => "TEST"
    case n => s"TEST-$n"
  }

  /**
   * L0: Standard Taktikos snowplow on slot gap.
   */
  val BaseConfig: VrfConfig = VrfConfig(
    lddCutoff          = 15,
    offset             = 0,
    precision          = 40,
    baselineDifficulty = Ratio(1, 20),
    amplitude          = Ratio(1, 2)
  )

  /**
   * L1-L9: Shifted exponential on base-block gaps.
   *
   * These parameters achieve:
   * - Target rates within 5% mean error
   * - Perfect burst resistance (threshold=0 at gap=1 for all levels)
   * - Clean 2x decay: L1 ~ 50%, L2 ~ 25%, L3 ~ 12.5%, ...
   *
   * Derived via analytical renewal theory + simulation refinement.
   * See paper/analysis/RESULTS.md for full derivation.
   */
  val SuperLevelConfigs: Vector[ShiftedExpConfig] = Vector(
    ShiftedExpConfig(level = 1, psi = 1, maxProb = 1.130555, scale = 0.500000),   // target 50.0% cond
    ShiftedExpConfig(level = 2, psi = 1, maxProb = 0.346157, scale = 0.500000),   // target 25.0%
    ShiftedExpConfig(level = 3, psi = 1, maxProb = 0.321504, scale = 7.921053),   // target 12.5%
    ShiftedExpConfig(level = 4, psi = 1, maxProb = 0.248923, scale = 30.342105),  // target 6.25%
    ShiftedExpConfig(level = 5, psi = 1, maxProb = 0.076907, scale = 27.526316),  // target 3.125%
    ShiftedExpConfig(level = 6, psi = 1, maxProb = 0.027017, scale = 40.500000),  // target 1.5625%
    ShiftedExpConfig(level = 7, psi = 1, maxProb = 0.012777, scale = 56.000000),  // target 0.78125%
    ShiftedExpConfig(level = 8, psi = 1, maxProb = 0.004451, scale = 64.000000),  // target 0.390625%
    ShiftedExpConfig(level = 9, psi = 1, maxProb = 0.001814, scale = 72.000000)   // target 0.195313%
  )

  // Legacy: flat conditional probabilities (for comparison/fallback)
  val ConditionalProbabilities: Vector[Double] =
    (0 until Count).toVector.map(level => 1.0 / (1 << level))

  /**
   * Per-level subchain entry: (lastHitBaseCount, height, tipHash).
   *
   * - lastHitBaseCount: L0 block count when this level last hit (for gap calculation)
   * - height: number of blocks in this level's subchain
   * - tipHash: H(block) of the most recent hit (for subchain linking)
   *
   * NOTE: Changed from (slot, height, hash) to (baseCount, height, hash) to support
   * base-block gap measurement for super levels.
   */
  type SubchainEntry = (Long, Long, Array[Byte])

  /** Genesis subchain state: baseCount=0, height=0, tip=zeros for all levels */
  val GenesisState: Vector[SubchainEntry] =
    Vector.fill(Count)((0L, 0L, new Array[Byte](32)))
}

// ---------------------------------------------------------------------------
// Simulation configuration
// ---------------------------------------------------------------------------

case class SimulationConfig(
  numStakers:    Int,
  totalSlots:    Long,
  slotsPerEpoch: Long,
  vrfConfig:     VrfConfig, // level-0 config (used for base eligibility)
  totalStake:    Long
)

// ---------------------------------------------------------------------------
// Per-slot results
// ---------------------------------------------------------------------------

/** Result for a single staker in a single slot */
case class StakerEligibility(
  stakerId:     Int,
  isEligible:   Boolean,    // level-0 eligible (produced a base block)
  threshold:    Double,     // level-0 threshold
  testValue:    Double,     // level-0 test value
  stakePercent: Double,
  levelHits:    Vector[Boolean] // which super levels (0..4) this staker hit
)

/** Result for a single slot */
case class SlotResult(
  slot:          Long,
  gap:           Long,  // base-level gap (slots since last base block)
  epoch:         Long,
  eligibleCount: Int,
  eligibilities: List[StakerEligibility],
  isFork:        Boolean,
  // Subchain state AFTER this slot: (lastHitSlot, height, tipHash) per level
  subchains:     Vector[SuperLevels.SubchainEntry]
)
