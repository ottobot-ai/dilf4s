package xyz.kd5ujc.taktikos

/**
 * Taktikos leader election types and configuration.
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

/** VRF configuration for the leader election */
case class VrfConfig(
  lddCutoff:          Int,   // Local Dynamic Difficulty cutoff (slots)
  precision:          Int,   // Precision for calculations
  baselineDifficulty: Ratio, // Difficulty when slotDiff > lddCutoff
  amplitude:          Ratio  // Maximum difficulty scale for LDD
)

/** Simulation configuration */
case class SimulationConfig(
  numStakers:    Int,
  totalSlots:    Long,
  slotsPerEpoch: Long,
  vrfConfig:     VrfConfig,
  totalStake:    Long
)

/** Result for a single staker in a single slot */
case class StakerEligibility(
  stakerId:     Int,
  isEligible:   Boolean,
  threshold:    Double,
  testValue:    Double,
  stakePercent: Double
)

/** Result for a single slot */
case class SlotResult(
  slot:          Long,
  gap:           Long, // slots since last block
  epoch:         Long,
  eligibleCount: Int,
  eligibilities: List[StakerEligibility],
  isFork:        Boolean // multiple eligible = unresolved fork
)
