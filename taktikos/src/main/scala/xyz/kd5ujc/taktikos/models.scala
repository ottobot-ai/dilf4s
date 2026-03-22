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
// NiPoPoW-style superblock levels
// ---------------------------------------------------------------------------

object SuperLevels {
  /** Number of superblock levels (0 = base, 1..4 = super) */
  val Count: Int = 5

  /**
   * Domain separation strings for each level's eligibility test.
   * Blake2b512(rho || domain) is the test hash — each level gets
   * an independent hash value from the same VRF output.
   */
  val Domains: Vector[String] = Vector("TEST", "TEST-1", "TEST-2", "TEST-3", "TEST-4")

  /**
   * Base LDD curve parameters. Each level derives its own curve from these:
   *
   *   Level μ: ψ_μ = γ_{μ-1}  (previous level's cutoff)
   *            γ_μ = baseCutoff × 2^μ
   *
   * The snowplow ramp for level μ is f(δ) = 0 for δ < ψ_μ,
   * then ramps linearly from ψ_μ to γ_μ. This means super levels
   * are dormant while the level below should be producing blocks,
   * and activate naturally once the gap exceeds the lower level's cutoff.
   *
   *   Level 0: ψ=0,   γ=15   (ramp 0–15,   active immediately)
   *   Level 1: ψ=15,  γ=30   (ramp 15–30,  dormant until gap > 15)
   *   Level 2: ψ=30,  γ=60   (ramp 30–60,  dormant until gap > 30)
   *   Level 3: ψ=60,  γ=120  (ramp 60–120, dormant until gap > 60)
   *   Level 4: ψ=120, γ=240  (ramp 120–240, dormant until gap > 120)
   */
  val BaseConfig: VrfConfig = VrfConfig(
    lddCutoff          = 15,
    offset             = 0,
    precision          = 40,
    baselineDifficulty = Ratio(1, 20),
    amplitude          = Ratio(1, 2)
  )

  /** Per-level LDD config: γ_μ = baseCutoff × 2^μ, ψ_μ = γ_{μ-1} (0 for level 0) */
  val LevelConfigs: Vector[VrfConfig] = (0 until Count).toVector.map { level =>
    val gamma = BaseConfig.lddCutoff * (1 << level)
    val psi   = if (level == 0) 0 else BaseConfig.lddCutoff * (1 << (level - 1))
    BaseConfig.copy(lddCutoff = gamma, offset = psi)
  }

  /**
   * Per-level subchain entry: (lastHitSlot, height, tipHash).
   *
   * - lastHitSlot: slot of the most recent hit at this level (for gap calculation)
   * - height: number of blocks in this level's subchain
   * - tipHash: H(block) of the most recent hit (for subchain linking)
   */
  type SubchainEntry = (Long, Long, Array[Byte])

  /** Genesis subchain state: slot=0, height=0, tip=zeros for all levels */
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
