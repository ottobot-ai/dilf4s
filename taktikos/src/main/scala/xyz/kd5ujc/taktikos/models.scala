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
  /**
   * Superblock levels: L0 (base) through L9.
   *
   * L0:     LDD snowplow on slot gap (primary chain growth driver)
   * L1-L3:  Flat conditional probability per base block (1/2, 1/4, 1/8)
   * L4-L9:  Self-regulating LDD on block-count gap (every 16, 32, 64, 128, 256, 512 blocks)
   */
  val Count: Int = 10

  /** Domain separation strings for each level */
  val Domains: Vector[String] = (0 until Count).toVector.map {
    case 0 => "TEST"
    case n => s"TEST-$n"
  }

  /**
   * L0 uses LDD snowplow on slot gap (primary chain growth driver).
   */
  val BaseConfig: VrfConfig = VrfConfig(
    lddCutoff          = 15,
    offset             = 0,
    precision          = 40,
    baselineDifficulty = Ratio(1, 20),
    amplitude          = Ratio(1, 2)
  )

  /**
   * L1-L9: flat conditional probability per base block.
   * P(Lμ | L0) = 1 / 2^μ — simple domain-separated coin flip.
   *
   *   L1: 1/2   → every 2nd block
   *   L2: 1/4   → every 4th block
   *   L3: 1/8   → every 8th block
   *   L4: 1/16  → every 16th block
   *   L5: 1/32  → every 32nd block
   *   L6: 1/64  → every 64th block
   *   L7: 1/128 → every 128th block
   *   L8: 1/256 → every 256th block
   *   L9: 1/512 → every 512th block
   */
  val ConditionalProbabilities: Vector[Double] =
    (0 until Count).toVector.map(level => 1.0 / (1 << level))

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
