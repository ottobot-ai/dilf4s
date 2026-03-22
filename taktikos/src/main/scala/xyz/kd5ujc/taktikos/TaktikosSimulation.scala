package xyz.kd5ujc.taktikos

import java.security.SecureRandom
import java.util.HexFormat

import cats.effect.{IO, IOApp, Ref}
import cats.implicits._

/**
 * Taktikos leader election simulation — Phase 1 with NiPoPoW-style superblocks.
 *
 * Each block that passes the base (level-0) eligibility test is also checked
 * against 4 additional, independently parameterized LDD curves (levels 1..4)
 * with domain-separated hashes. Blocks form embedded subchains at each level.
 *
 * Block headers track subchain state as Vector[(height, tipHash)] —
 * coupled tuples, one per level. On a hit, height increments and tipHash = H(this).
 * On a miss, the tuple carries forward unchanged.
 */
object TaktikosSimulation extends IOApp.Simple {

  val config: SimulationConfig = SimulationConfig(
    numStakers    = 5,
    totalSlots    = 10000,
    slotsPerEpoch = 100,
    vrfConfig     = SuperLevels.BaseConfig,
    totalStake    = 10000
  )

  val stakeDistribution: List[Long] = List(3000L, 2500L, 2000L, 1500L, 1000L)

  private val hex = HexFormat.of()

  def run: IO[Unit] =
    for {
      stakers <- initializeStakers(config)

      genesisEta = Eta(LeaderElection.blake2b256("taktikos-genesis-eta".getBytes("UTF-8")))

      _ <- IO.println(s"Starting Taktikos simulation with ${config.numStakers} stakers, ${config.totalSlots} slots")
      _ <- IO.println(s"Stake: ${stakers.map(s => s"S${s.id}=${s.stake}").mkString(", ")}")
      _ <- IO.println(s"Super-levels: ${SuperLevels.Count} (domains: ${SuperLevels.Domains.mkString(", ")})")
      _ <- IO.println(s"L0: LDD snowplow (amplitude=${SuperLevels.BaseConfig.amplitude}, baseline=${SuperLevels.BaseConfig.baselineDifficulty}, cutoff=${SuperLevels.BaseConfig.lddCutoff})")
      _ <- IO.println(s"L1-L9: shifted exponential on base-block gap (ψ=1, per-level maxProb/scale)")
      _ <- IO.println("---")

      results <- simulateSlots(stakers, config, genesisEta)

      _ <- printSummary(results, stakers, config)
    } yield ()

  def initializeStakers(config: SimulationConfig): IO[List[Staker]] = IO {
    val random = new SecureRandom()
    (0 until config.numStakers).toList.map { id =>
      val sk = new Array[Byte](32)
      random.nextBytes(sk)
      val vk = LeaderElection.deriveVrfVK(sk)
      Staker(id, sk, vk, stakeDistribution(id))
    }
  }

  /**
   * Simple block hash: Blake2b-256(slot bytes ++ staker id byte ++ parent subchain tips).
   * Good enough for the simulation — deterministic from the chain state.
   */
  def computeBlockHash(slot: Long, stakerId: Int, subchains: Vector[SuperLevels.SubchainEntry]): Array[Byte] = {
    val payload = BigInt(slot).toByteArray ++ Array(stakerId.toByte) ++ subchains.flatMap(_._3)
    LeaderElection.blake2b256(payload)
  }

  def simulateSlots(
    stakers:    List[Staker],
    config:     SimulationConfig,
    genesisEta: Eta
  ): IO[List[SlotResult]] =
    for {
      etaRef           <- Ref.of[IO, Eta](genesisEta)
      epochRef         <- Ref.of[IO, Long](0L)
      rhoNoncesRef     <- Ref.of[IO, List[Array[Byte]]](Nil)
      subchainsRef     <- Ref.of[IO, Vector[SuperLevels.SubchainEntry]](SuperLevels.GenesisState)
      baseCountRef     <- Ref.of[IO, Long](0L)  // Cumulative L0 block count
      slotGapRef       <- Ref.of[IO, Long](1L)  // Slots since last L0 block

      results <- (1L to config.totalSlots).toList.traverse { slot =>
        for {
          currentEpoch <- epochRef.get
          newEpoch      = (slot - 1) / config.slotsPerEpoch

          // Epoch transition
          _ <- if (newEpoch > currentEpoch) {
            for {
              nonces      <- rhoNoncesRef.get
              previousEta <- etaRef.get
              nextEta      = LeaderElection.computeNextEta(previousEta, newEpoch, nonces.reverse)
              _           <- etaRef.set(nextEta)
              _           <- epochRef.set(newEpoch)
              _           <- rhoNoncesRef.set(Nil)
              _           <- IO.println(f"  *** Epoch $newEpoch%2d (slot $slot%4d) — eta rotated ***")
            } yield ()
          } else IO.unit

          activeEta        <- etaRef.get
          currentSubchains <- subchainsRef.get
          currentBaseCount <- baseCountRef.get
          currentSlotGap   <- slotGapRef.get

          // Check all stakers at ALL levels using per-level LDD
          eligibilities = stakers.map { staker =>
            LeaderElection.checkEligibilityAllLevels(
              staker, slot, currentSlotGap, currentBaseCount,
              currentSubchains, activeEta, config.totalStake
            )
          }

          eligible = eligibilities.filter(_.isEligible) // base-eligible (L0 hit)
          isFork   = eligible.size > 1

          // Update subchain state and counters from the first eligible staker
          newSubchains <- eligible.headOption match {
            case Some(leader) =>
              val newBaseCount = currentBaseCount + 1
              val blockHash = computeBlockHash(slot, leader.stakerId, currentSubchains)
              val updated   = LeaderElection.updateSubchains(currentSubchains, newBaseCount, blockHash, leader.levelHits)
              subchainsRef.set(updated) *> baseCountRef.set(newBaseCount) *> slotGapRef.set(1L) *> IO.pure(updated)
            case None =>
              slotGapRef.update(_ + 1) *> IO.pure(currentSubchains)
          }

          result = SlotResult(slot, currentSlotGap, newEpoch, eligible.size, eligibilities, isFork, newSubchains)

          // Accumulate rho nonce hashes
          _ <- eligible.traverse_ { leader =>
            val rho = LeaderElection.rhoForSlot(
              stakers.find(_.id == leader.stakerId).get.vrfSK, slot, activeEta
            )
            rhoNoncesRef.update(LeaderElection.rhoNonceHash(rho) :: _)
          }

          _ <- printSlotResult(result)
        } yield result
      }
    } yield results

  def printSlotResult(result: SlotResult): IO[Unit] = {
    // For 10k slots, only print milestones
    if (result.slot % 1000 == 0) {
      IO.println(f"Slot ${result.slot}%5d: heights=${heightString(result.subchains)}")
    } else IO.unit
  }

  /** Format level hits as e.g. "[0,2,4]" showing which levels were hit */
  def levelHitString(hits: Vector[Boolean]): String = {
    val levels = hits.zipWithIndex.collect { case (true, i) => i.toString }
    s"L[${levels.mkString(",")}]"
  }

  /** Format subchain heights as e.g. "[145,73,38,18,10]" */
  def heightString(subchains: Vector[SuperLevels.SubchainEntry]): String =
    s"[${subchains.map(_._2).mkString(",")}]"

  def printSummary(
    results: List[SlotResult],
    stakers: List[Staker],
    config:  SimulationConfig
  ): IO[Unit] = {
    val totalSlots     = results.size
    val slotsWithBlock = results.count(_.eligibleCount > 0)
    val emptySlots     = totalSlots - slotsWithBlock
    val singleLeader   = results.count(_.eligibleCount == 1)
    val forkSlots      = results.count(_.isFork)
    val numEpochs      = results.last.epoch + 1

    val blocksByStaker = results
      .flatMap(_.eligibilities.filter(_.isEligible))
      .groupBy(_.stakerId)
      .view.mapValues(_.size).toMap

    val totalBlocks = blocksByStaker.values.sum

    // Gap stats
    val gaps      = results.filter(_.eligibleCount > 0).map(_.gap)
    val avgGap    = if (gaps.nonEmpty) gaps.sum.toDouble / gaps.size else 0.0
    val medianGap = if (gaps.nonEmpty) { val s = gaps.sorted; s(s.size / 2) } else 0L
    val maxGap    = gaps.maxOption.getOrElse(0L)

    // Final subchain state
    val finalSubchains = results.last.subchains

    // Per-level hit counts from final subchain heights (accurate, includes non-block-slot hits)
    val levelHitCounts = finalSubchains.map(_._2.toInt)

    val fillRate = slotsWithBlock.toDouble / totalSlots * 100

    for {
      _ <- IO.println("")
      _ <- IO.println("=" * 70)
      _ <- IO.println("  TAKTIKOS SIMULATION SUMMARY (with NiPoPoW Superblocks)")
      _ <- IO.println("=" * 70)
      _ <- IO.println(f"Total slots:       $totalSlots%d")
      _ <- IO.println(f"Slots with blocks: $slotsWithBlock%d ($fillRate%.1f%% fill rate)")
      _ <- IO.println(f"  Single leader:   $singleLeader%d")
      _ <- IO.println(f"  Fork (multi):    $forkSlots%d")
      _ <- IO.println(f"Empty slots:       $emptySlots%d")
      _ <- IO.println(f"Epochs:            $numEpochs%d")
      _ <- IO.println(f"Total blocks:      $totalBlocks%d (includes fork duplicates)")
      _ <- IO.println("")
      _ <- IO.println("--- Slot Gap Statistics ---")
      _ <- IO.println(f"  Mean: $avgGap%.2f | Median: $medianGap%d | Max: $maxGap%d")
      _ <- IO.println("")
      _ <- IO.println("--- Block Production by Staker ---")
      _ <- stakers.traverse_ { s =>
        val blocks     = blocksByStaker.getOrElse(s.id, 0)
        val pct        = if (totalBlocks > 0) blocks.toDouble / totalBlocks * 100 else 0.0
        val stakeRatio = s.stake.toDouble / config.totalStake * 100
        IO.println(f"  S${s.id} ($stakeRatio%.0f%% stake): $blocks%3d blocks ($pct%.1f%%)")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Superblock Level Analysis ---")
      _ <- IO.println(f"  ${"Level"}%-8s ${"Hits"}%6s ${"Rate"}%8s ${"Avg Gap"}%10s ${"Target Gap"}%12s ${"Domain"}%-10s")
      _ <- IO.println("  " + "-" * 58)
      _ <- (0 until SuperLevels.Count).toList.traverse_ { level =>
        val hits = levelHitCounts(level)
        val rate = if (totalSlots > 0) hits.toDouble / totalSlots * 100 else 0.0
        val avgLevelGap = if (hits > 0) totalSlots.toDouble / hits else 0.0
        val targetGap = 7 * math.pow(2.0, level.toDouble).toInt
        IO.println(f"  Level $level%-3d $hits%6d $rate%7.1f%% $avgLevelGap%9.1f $targetGap%10d   ${SuperLevels.Domains(level)}%-10s")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Final Subchain State (lastSlot, height, tipHash) ---")
      _ <- finalSubchains.zipWithIndex.toList.traverse_ { case ((lastSlot, height, tip), level) =>
        val tipHex = hex.formatHex(tip).take(16)
        IO.println(f"  Level $level: slot=$lastSlot%4d  height=$height%4d  tip=$tipHex...")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Superblock Distribution Histogram ---")
      _ <- (0 until SuperLevels.Count).toList.traverse_ { level =>
        val hits = levelHitCounts(level)
        val bar  = "█" * (hits / 3).max(1)
        IO.println(f"  L$level: $hits%4d $bar")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Fork Analysis ---")
      _ <- if (forkSlots > 0) {
        val forkResults = results.filter(_.isFork).take(20) // cap at 20 for readability
        forkResults.traverse_ { r =>
          val names = r.eligibilities.filter(_.isEligible)
            .map(e => s"S${e.stakerId}${levelHitString(e.levelHits)}")
            .mkString(", ")
          IO.println(f"  Slot ${r.slot}%4d [gap=${r.gap}%2d]: $names")
        } *> (if (forkSlots > 20) IO.println(s"  ... and ${forkSlots - 20} more") else IO.unit)
      } else IO.println("  No forks!")
      _ <- IO.println("=" * 70)
    } yield ()
  }
}
