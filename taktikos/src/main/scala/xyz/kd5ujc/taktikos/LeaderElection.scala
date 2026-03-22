package xyz.kd5ujc.taktikos

import xyz.kd5ujc.vrf.EcVrf25519

import org.bouncycastle.crypto.digests.Blake2bDigest

/**
 * Taktikos leader election logic implementing the VRF-based
 * threshold mechanism from Bifrost/Topl.
 */
object LeaderElection {

  private val vrf = new EcVrf25519

  /**
   * Compute Blake2b-256 hash.
   */
  def blake2b256(data: Array[Byte]): Array[Byte] = {
    val digest = new Blake2bDigest(256)
    digest.update(data, 0, data.length)
    val out = new Array[Byte](32)
    digest.doFinal(out, 0)
    out
  }

  /**
   * Compute Blake2b-512 hash.
   */
  def blake2b512(data: Array[Byte]): Array[Byte] = {
    val digest = new Blake2bDigest(512)
    digest.update(data, 0, data.length)
    val out = new Array[Byte](64)
    digest.doFinal(out, 0)
    out
  }

  /**
   * Generate VRF proof for a given slot.
   * Message format: eta_bytes ++ BigInt(slot).toByteArray (big-endian)
   */
  def vrfProofForSlot(vrfSK: Array[Byte], slot: Long, eta: Eta): Array[Byte] = {
    val message = eta.bytes ++ BigInt(slot).toByteArray
    vrf.vrfProof(vrfSK, message)
  }

  /**
   * Compute rho (VRF output hash) for a given slot.
   * Returns 64-byte hash from proofToHash.
   */
  def rhoForSlot(vrfSK: Array[Byte], slot: Long, eta: Eta): Rho = {
    val proof = vrfProofForSlot(vrfSK, slot, eta)
    vrf.vrfProofToHash(proof) match {
      case Some(hash) => Rho(hash)
      case None       => throw new RuntimeException(s"Failed to compute rho for slot $slot")
    }
  }

  /**
   * Calculate the threshold for leader eligibility using LDD (Local Dynamic Difficulty).
   *
   * The difficulty curve is:
   *   - If slotDiff > lddCutoff: baselineDifficulty
   *   - Otherwise: (slotDiff / lddCutoff) * amplitude
   *
   * The threshold is: 1 - (1 - difficulty)^relativeStake
   */
  def getThreshold(relativeStake: Double, slotDiff: Long, config: VrfConfig): Double = {
    val difficulty: Double =
      if (slotDiff > config.lddCutoff) config.baselineDifficulty.toDouble
      else (slotDiff.toDouble / config.lddCutoff) * config.amplitude.toDouble

    if (difficulty >= 1.0) 1.0
    else 1.0 - math.pow(1.0 - difficulty, relativeStake)
  }

  /**
   * Test if a staker is the slot leader.
   *
   * The test computes a hash from rho and compares against the threshold:
   *   testHash = Blake2b-512(rho.bytes ++ "TEST".getBytes)
   *   testValue = testHash as unsigned BigInt / 2^512
   *   eligible if threshold > testValue
   */
  def isSlotLeader(threshold: Double, rho: Rho): (Boolean, Double) = {
    val testHash  = blake2b512(rho.bytes ++ "TEST".getBytes("UTF-8"))
    val testValue = BigInt(1, testHash) // unsigned big-endian
    // Use BigDecimal for precision in division
    val normalization = BigDecimal(BigInt(2).pow(512))
    val test          = (BigDecimal(testValue) / normalization).toDouble

    (threshold > test, test)
  }

  /**
   * Derive VRF verification key from secret key.
   */
  def deriveVrfVK(sk: Array[Byte]): Array[Byte] =
    vrf.getVerificationKey(sk)

  /**
   * Check eligibility for a single staker in a single slot.
   */
  def checkEligibility(
    staker:     Staker,
    slot:       Long,
    slotDiff:   Long,
    eta:        Eta,
    totalStake: Long,
    config:     VrfConfig
  ): StakerEligibility = {
    val relativeStake = staker.stake.toDouble / totalStake.toDouble
    val threshold     = getThreshold(relativeStake, slotDiff, config)
    val rho           = rhoForSlot(staker.vrfSK, slot, eta)
    val (eligible, testValue) = isSlotLeader(threshold, rho)

    StakerEligibility(
      stakerId     = staker.id,
      isEligible   = eligible,
      threshold    = threshold,
      testValue    = testValue,
      stakePercent = relativeStake * 100.0
    )
  }
}
