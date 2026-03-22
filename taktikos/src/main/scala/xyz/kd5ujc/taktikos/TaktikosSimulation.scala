package xyz.kd5ujc.taktikos

import java.security.SecureRandom

import cats.effect.{IO, IOApp, Ref}
import cats.implicits._

/**
 * Taktikos leader election simulation.
 *
 * Simulates the PoS leader election from Ouroboros Taktikos where each staker
 * checks every slot whether they're eligible to produce a block using
 * a VRF + threshold mechanism (Local Dynamic Difficulty).
 *
 * Phase 1: single consistent view with maxvalid-tk tiebreaker (lowest test value wins).
 * No networking — all peers compute the same deterministic result.
 */
object TaktikosSimulation extends IOApp.Simple {

  val config: SimulationConfig = SimulationConfig(
    numStakers    = 5,
    totalSlots    = 1000,
    slotsPerEpoch = 100,
    vrfConfig = VrfConfig(
      lddCutoff          = 15,
      precision          = 40,
      baselineDifficulty = Ratio(1, 20),
      amplitude          = Ratio(1, 2)
    ),
    totalStake = 10000
  )

  // Stake distribution: 30/25/20/15/10 split
  val stakeDistribution: List[Long] = List(3000L, 2500L, 2000L, 1500L, 1000L)

  def run: IO[Unit] =
    for {
      stakers <- initializeStakers(config)

      genesisEta = Eta(LeaderElection.blake2b256("taktikos-genesis-eta".getBytes("UTF-8")))

      _ <- IO.println(
        s"Starting Taktikos simulation with ${config.numStakers} stakers over ${config.totalSlots} slots"
      )
      _ <- IO.println(s"Stake distribution: ${stakers.map(s => s"S${s.id}=${s.stake}").mkString(", ")}")
      _ <- IO.println(
        s"VRF Config: lddCutoff=${config.vrfConfig.lddCutoff}, " +
        s"baseline=${config.vrfConfig.baselineDifficulty}, " +
        s"amplitude=${config.vrfConfig.amplitude}, " +
        s"slotsPerEpoch=${config.slotsPerEpoch}"
      )
      _ <- IO.println("---")

      results <- simulateSlots(stakers, config, genesisEta)

      _ <- printSummary(results, stakers, config)
    } yield ()

  def initializeStakers(config: SimulationConfig): IO[List[Staker]] = IO {
    val random = new SecureRandom()
    (0 until config.numStakers).toList.map { id =>
      val sk    = new Array[Byte](32)
      random.nextBytes(sk)
      val vk    = LeaderElection.deriveVrfVK(sk)
      val stake = stakeDistribution(id)
      Staker(id, sk, vk, stake)
    }
  }

  def simulateSlots(
    stakers:    List[Staker],
    config:     SimulationConfig,
    genesisEta: Eta
  ): IO[List[SlotResult]] =
    for {
      lastBlockSlotRef <- Ref.of[IO, Long](0L)
      etaRef           <- Ref.of[IO, Eta](genesisEta)
      epochRef         <- Ref.of[IO, Long](0L)
      // Accumulate rho nonce hashes for eta calculation
      rhoNoncesRef     <- Ref.of[IO, List[Array[Byte]]](Nil)

      results <- (1L to config.totalSlots).toList.traverse { slot =>
        for {
          lastBlockSlot <- lastBlockSlotRef.get
          eta           <- etaRef.get
          currentEpoch  <- epochRef.get
          slotDiff       = slot - lastBlockSlot
          newEpoch       = (slot - 1) / config.slotsPerEpoch

          // Epoch transition
          _ <- if (newEpoch > currentEpoch) {
            for {
              nonces     <- rhoNoncesRef.get
              previousEta <- etaRef.get
              nextEta     = LeaderElection.computeNextEta(previousEta, newEpoch, nonces.reverse)
              _          <- etaRef.set(nextEta)
              _          <- epochRef.set(newEpoch)
              _          <- rhoNoncesRef.set(Nil)
              _          <- IO.println(f"  *** Epoch $newEpoch%2d (slot $slot%4d) — eta rotated ***")
            } yield ()
          } else IO.unit

          activeEta <- etaRef.get

          // Check all stakers
          eligibilities = stakers.map { staker =>
            LeaderElection.checkEligibility(staker, slot, slotDiff, activeEta, config.totalStake, config.vrfConfig)
          }

          eligible = eligibilities.filter(_.isEligible)
          // maxvalid-tk tiebreaker: lowest test value wins
          canonical = LeaderElection.selectCanonicalLeader(eligible)

          result = SlotResult(slot, slotDiff, newEpoch, eligible.size, eligibilities, canonical)

          // Update state
          _ <- if (canonical.isDefined) lastBlockSlotRef.set(slot) else IO.unit

          // Accumulate rho nonce hashes from canonical leader (or first eligible)
          _ <- canonical.traverse_ { leader =>
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
    val eligible = result.eligibilities.filter(_.isEligible)

    // Only print interesting slots: elections and long gaps
    eligible match {
      case Nil =>
        // Print every 50th empty slot or when gap hits baseline threshold
        if (result.gap == result.eligibilities.headOption.map(_ =>
            result.eligibilities.head.threshold).map(_ => 16L).getOrElse(16L) ||
            result.slot % 100 == 0)
          IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] No leader (max threshold: ${result.eligibilities.map(_.threshold).max}%.4f)")
        else IO.unit

      case _ :: Nil =>
        val w = result.canonicalLeader.get
        IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] S${w.stakerId} elected (thr=${w.threshold}%.4f test=${w.testValue}%.4f stake=${w.stakePercent}%.0f%%)")

      case multi =>
        val w = result.canonicalLeader.get
        val others = multi.filterNot(_.stakerId == w.stakerId).map(e => s"S${e.stakerId}").mkString(",")
        IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] S${w.stakerId} elected [tiebreak over $others] (thr=${w.threshold}%.4f test=${w.testValue}%.4f)")
    }
  }

  def printSummary(
    results: List[SlotResult],
    stakers: List[Staker],
    config:  SimulationConfig
  ): IO[Unit] = {
    val totalSlots     = results.size
    val blocksProduced = results.count(_.canonicalLeader.isDefined)
    val emptySlots     = totalSlots - blocksProduced
    val multiLeader    = results.count(_.eligibleCount > 1)
    val numEpochs      = results.last.epoch + 1

    // Count blocks per staker (canonical only)
    val blocksByStaker = results
      .flatMap(_.canonicalLeader)
      .groupBy(_.stakerId)
      .view.mapValues(_.size).toMap

    // Slot gap distribution
    val gaps = results.filter(_.canonicalLeader.isDefined).map(_.gap)
    val avgGap    = if (gaps.nonEmpty) gaps.sum.toDouble / gaps.size else 0.0
    val medianGap = if (gaps.nonEmpty) { val s = gaps.sorted; s(s.size / 2) } else 0L
    val maxGap    = gaps.maxOption.getOrElse(0L)
    val minGap    = gaps.minOption.getOrElse(0L)
    val p99Gap    = if (gaps.nonEmpty) { val s = gaps.sorted; s((s.size * 0.99).toInt.min(s.size - 1)) } else 0L

    // Blocks per epoch
    val blocksPerEpoch = results
      .filter(_.canonicalLeader.isDefined)
      .groupBy(_.epoch)
      .view.mapValues(_.size).toMap

    val fillRate = blocksProduced.toDouble / totalSlots * 100

    for {
      _ <- IO.println("")
      _ <- IO.println("=" * 60)
      _ <- IO.println("  TAKTIKOS SIMULATION SUMMARY")
      _ <- IO.println("=" * 60)
      _ <- IO.println(f"Total slots:      $totalSlots%d")
      _ <- IO.println(f"Blocks produced:  $blocksProduced%d ($fillRate%.1f%% fill rate)")
      _ <- IO.println(f"Empty slots:      $emptySlots%d")
      _ <- IO.println(f"Multi-eligible:   $multiLeader%d (resolved by tiebreaker)")
      _ <- IO.println(f"Epochs:           $numEpochs%d")
      _ <- IO.println("")
      _ <- IO.println("--- Slot Gap Statistics ---")
      _ <- IO.println(f"  Mean:   $avgGap%.2f slots")
      _ <- IO.println(f"  Median: $medianGap%d slots")
      _ <- IO.println(f"  Min:    $minGap%d  Max: $maxGap%d  P99: $p99Gap%d")
      _ <- IO.println("")
      _ <- IO.println("--- Block Production by Staker ---")
      _ <- stakers.traverse_ { s =>
        val blocks     = blocksByStaker.getOrElse(s.id, 0)
        val pct        = if (blocksProduced > 0) blocks.toDouble / blocksProduced * 100 else 0.0
        val stakeRatio = s.stake.toDouble / config.totalStake * 100
        IO.println(f"  S${s.id} ($stakeRatio%.0f%% stake): $blocks%3d blocks ($pct%.1f%% of total)")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Blocks per Epoch ---")
      _ <- (0L until numEpochs).toList.traverse_ { e =>
        val blocks = blocksPerEpoch.getOrElse(e, 0)
        val bar    = "█" * (blocks / 2).max(1)
        IO.println(f"  Epoch $e%2d: $blocks%3d blocks $bar")
      }
      _ <- IO.println("=" * 60)
    } yield ()
  }
}
