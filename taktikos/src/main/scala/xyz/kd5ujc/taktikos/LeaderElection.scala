package xyz.kd5ujc.taktikos

import xyz.kd5ujc.vrf.EcVrf25519

import org.bouncycastle.crypto.digests.Blake2bDigest

/**
 * Taktikos leader election logic implementing the VRF-based
 * threshold mechanism with NiPoPoW-style multi-level superblock tests.
 */
object LeaderElection {

  private val vrf = new EcVrf25519

  // ------- Hashing -------

  def blake2b256(data: Array[Byte]): Array[Byte] = {
    val digest = new Blake2bDigest(256)
    digest.update(data, 0, data.length)
    val out = new Array[Byte](32)
    digest.doFinal(out, 0)
    out
  }

  def blake2b512(data: Array[Byte]): Array[Byte] = {
    val digest = new Blake2bDigest(512)
    digest.update(data, 0, data.length)
    val out = new Array[Byte](64)
    digest.doFinal(out, 0)
    out
  }

  // ------- VRF -------

  def vrfProofForSlot(vrfSK: Array[Byte], slot: Long, eta: Eta): Array[Byte] = {
    val message = eta.bytes ++ BigInt(slot).toByteArray
    vrf.vrfProof(vrfSK, message)
  }

  def rhoForSlot(vrfSK: Array[Byte], slot: Long, eta: Eta): Rho = {
    val proof = vrfProofForSlot(vrfSK, slot, eta)
    vrf.vrfProofToHash(proof) match {
      case Some(hash) => Rho(hash)
      case None       => throw new RuntimeException(s"Failed to compute rho for slot $slot")
    }
  }

  def deriveVrfVK(sk: Array[Byte]): Array[Byte] =
    vrf.getVerificationKey(sk)

  // ------- Threshold (LDD) -------

  /**
   * Calculate the threshold for leader eligibility using the full snowplow LDD.
   *
   * Three regimes from the Taktikos paper:
   *   f(δ) = 0                                  if δ < ψ
   *          fA × (δ - ψ) / (γ - ψ)            if ψ ≤ δ < γ
   *          fB                                  if δ ≥ γ
   *
   * threshold = 1 - (1 - f(δ))^relativeStake
   */
  def getThreshold(relativeStake: Double, slotDiff: Long, config: VrfConfig): Double = {
    val psi   = config.offset
    val gamma = config.lddCutoff
    val fA    = config.amplitude.toDouble
    val fB    = config.baselineDifficulty.toDouble

    val difficulty: Double =
      if (slotDiff < psi) 0.0
      else if (slotDiff < gamma) fA * (slotDiff - psi).toDouble / (gamma - psi).toDouble
      else fB

    if (difficulty <= 0.0) 0.0
    else if (difficulty >= 1.0) 1.0
    else 1.0 - math.pow(1.0 - difficulty, relativeStake)
  }

  // ------- Eligibility test (single level) -------

  /**
   * Test eligibility for a given level.
   * Returns (isEligible, testValue).
   *
   *   testHash  = Blake2b-512(rho || domain)
   *   testValue = testHash / 2^512
   *   eligible  = threshold > testValue
   */
  def isSlotLeaderForLevel(threshold: Double, rho: Rho, domain: String): (Boolean, Double) = {
    val testHash  = blake2b512(rho.bytes ++ domain.getBytes("UTF-8"))
    val testValue = BigInt(1, testHash) // unsigned big-endian
    val norm      = BigDecimal(BigInt(2).pow(512))
    val test      = (BigDecimal(testValue) / norm).toDouble
    (threshold > test, test)
  }

  // ------- Multi-level eligibility -------

  /**
   * Check eligibility at all levels using per-level LDD.
   *
   * L0:    LDD snowplow on SLOT gap (primary chain growth)
   * L1-L9: Shifted exponential on BASE-BLOCK gap (genuine difficulty shaping)
   *
   * Key insight: super levels measure gaps in L0 blocks, not slots.
   * This solves the L0-gating frequency problem while providing burst resistance.
   *
   * @param baseBlockCount Current cumulative L0 block count (needed for super-level gaps)
   */
  def checkEligibilityAllLevels(
    staker:         Staker,
    slot:           Long,
    slotGap:        Long,                             // Slots since last L0 block (for L0 threshold)
    baseBlockCount: Long,                             // Current L0 block count (for super-level gaps)
    subchains:      Vector[SuperLevels.SubchainEntry], // (lastHitBaseCount, height, tipHash)
    eta:            Eta,
    totalStake:     Long
  ): StakerEligibility = {
    val relativeStake = staker.stake.toDouble / totalStake.toDouble
    val rho           = rhoForSlot(staker.vrfSK, slot, eta)

    // Level-0: LDD snowplow on SLOT gap
    val baseThreshold = getThreshold(relativeStake, slotGap, SuperLevels.BaseConfig)
    val (eligible0, test0) = isSlotLeaderForLevel(baseThreshold, rho, SuperLevels.Domains(0))

    if (!eligible0) {
      StakerEligibility(
        stakerId     = staker.id,
        isEligible   = false,
        threshold    = baseThreshold,
        testValue    = test0,
        stakePercent = relativeStake * 100.0,
        levelHits    = Vector.fill(SuperLevels.Count)(false)
      )
    } else {
      // Base-eligible — test super levels with shifted exponential on BASE-BLOCK gaps
      val newBaseCount = baseBlockCount + 1 // This block will be a new L0 block
      
      val levelHits = (0 until SuperLevels.Count).toVector.map { level =>
        if (level == 0) {
          true // L0 already confirmed eligible
        } else {
          // Gap = base blocks since this level last hit
          val lastHitBaseCount = subchains(level)._1
          val gap = newBaseCount - lastHitBaseCount
          
          // Shifted exponential threshold
          val config = SuperLevels.SuperLevelConfigs(level - 1)
          val threshold = config.threshold(gap)
          
          val (hit, _) = isSlotLeaderForLevel(threshold, rho, SuperLevels.Domains(level))
          hit
        }
      }

      StakerEligibility(
        stakerId     = staker.id,
        isEligible   = true,
        threshold    = baseThreshold,
        testValue    = test0,
        stakePercent = relativeStake * 100.0,
        levelHits    = levelHits
      )
    }
  }

  /**
   * Legacy version using flat conditional probabilities.
   * Kept for comparison and fallback.
   */
  def checkEligibilityAllLevelsFlat(
    staker:     Staker,
    slot:       Long,
    slotGap:    Long,
    subchains:  Vector[SuperLevels.SubchainEntry],
    eta:        Eta,
    totalStake: Long
  ): StakerEligibility = {
    val relativeStake = staker.stake.toDouble / totalStake.toDouble
    val rho           = rhoForSlot(staker.vrfSK, slot, eta)

    val baseThreshold = getThreshold(relativeStake, slotGap, SuperLevels.BaseConfig)
    val (eligible0, test0) = isSlotLeaderForLevel(baseThreshold, rho, SuperLevels.Domains(0))

    if (!eligible0) {
      StakerEligibility(
        stakerId     = staker.id,
        isEligible   = false,
        threshold    = baseThreshold,
        testValue    = test0,
        stakePercent = relativeStake * 100.0,
        levelHits    = Vector.fill(SuperLevels.Count)(false)
      )
    } else {
      val levelHits = (0 until SuperLevels.Count).toVector.map { level =>
        if (level == 0) true
        else {
          val prob = SuperLevels.ConditionalProbabilities(level)
          val (hit, _) = isSlotLeaderForLevel(prob, rho, SuperLevels.Domains(level))
          hit
        }
      }

      StakerEligibility(
        stakerId     = staker.id,
        isEligible   = true,
        threshold    = baseThreshold,
        testValue    = test0,
        stakePercent = relativeStake * 100.0,
        levelHits    = levelHits
      )
    }
  }

  // ------- Subchain state update -------

  /**
   * Update subchain state when a block is produced.
   *
   * For each level the block hits: set lastHitBaseCount, increment height, set tip = H(this block).
   * For each level it misses: carry forward unchanged.
   *
   * @param baseBlockCount The new cumulative L0 block count (after this block is added)
   */
  def updateSubchains(
    current:        Vector[SuperLevels.SubchainEntry],
    baseBlockCount: Long,
    blockHash:      Array[Byte],
    levelHits:      Vector[Boolean]
  ): Vector[SuperLevels.SubchainEntry] =
    current.zip(levelHits).map {
      case ((_, height, _), true)  => (baseBlockCount, height + 1, blockHash)
      case (unchanged,      false) => unchanged
    }

  // ------- Epoch eta -------

  def rhoNonceHash(rho: Rho): Array[Byte] =
    blake2b512(rho.bytes ++ "NONCE".getBytes("UTF-8"))

  def computeNextEta(previousEta: Eta, epoch: Long, rhoNonceHashes: List[Array[Byte]]): Eta = {
    val epochBytes = BigInt(epoch).toByteArray
    val payload    = previousEta.bytes ++ epochBytes ++ rhoNonceHashes.flatten
    Eta(blake2b256(payload))
  }

  // ------- Superblock chain selection weight (lexicographic, highest level first) -------

  /**
   * Compare two subchain state vectors lexicographically, highest level first.
   * Returns > 0 if `a` is heavier, < 0 if `b` is heavier, 0 if equal.
   */
  def compareSubchainWeight(
    a: Vector[SuperLevels.SubchainEntry],
    b: Vector[SuperLevels.SubchainEntry]
  ): Int = {
    // Walk from highest level (4) down to level 1 — level 0 is already covered by chain length
    var level = SuperLevels.Count - 1
    while (level >= 1) {
      val diff = a(level)._2.compareTo(b(level)._2) // compare heights
      if (diff != 0) return diff
      level -= 1
    }
    0
  }
}
