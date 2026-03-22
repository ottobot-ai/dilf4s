package xyz.kd5ujc.taktikos

import java.security.SecureRandom

import cats.effect.{IO, IOApp, Ref}
import cats.implicits._

/**
 * Taktikos leader election simulation — Phase 1.
 *
 * Simulates the PoS leader election from Ouroboros Taktikos where each staker
 * checks every slot whether they're eligible to produce a block using
 * a VRF + threshold mechanism (Local Dynamic Difficulty).
 *
 * Phase 1: no chain, no networking. Multi-eligible slots are genuine forks —
 * they can only be resolved by maxvalid-tk chain selection in Phase 2:
 *   - Longer chain wins
 *   - Equal length → lower head slot wins
 *
 * For now we track fork slots and report them as unresolved.
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
      rhoNoncesRef     <- Ref.of[IO, List[Array[Byte]]](Nil)

      results <- (1L to config.totalSlots).toList.traverse { slot =>
        for {
          lastBlockSlot <- lastBlockSlotRef.get
          currentEpoch  <- epochRef.get
          slotDiff       = slot - lastBlockSlot
          newEpoch       = (slot - 1) / config.slotsPerEpoch

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

          activeEta <- etaRef.get

          // Check all stakers
          eligibilities = stakers.map { staker =>
            LeaderElection.checkEligibility(staker, slot, slotDiff, activeEta, config.totalStake, config.vrfConfig)
          }

          eligible = eligibilities.filter(_.isEligible)
          isFork   = eligible.size > 1

          result = SlotResult(slot, slotDiff, newEpoch, eligible.size, eligibilities, isFork)

          // Any eligible staker means a block was produced (advances the chain)
          // In a fork, BOTH produce blocks — gap resets either way
          _ <- if (eligible.nonEmpty) lastBlockSlotRef.set(slot) else IO.unit

          // Accumulate rho nonce hashes from ALL eligible stakers
          // (in Phase 2, only the canonical chain's blocks contribute to eta)
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
    val eligible = result.eligibilities.filter(_.isEligible)

    eligible match {
      case Nil =>
        // Only print milestone empty slots
        if (result.slot % 100 == 0)
          IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] No leader (max thr: ${result.eligibilities.map(_.threshold).max}%.4f)")
        else IO.unit

      case single :: Nil =>
        IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] S${single.stakerId} elected (thr=${single.threshold}%.4f test=${single.testValue}%.4f stake=${single.stakePercent}%.0f%%)")

      case multi =>
        val names = multi.map(e => f"S${e.stakerId}").mkString(", ")
        IO.println(f"Slot ${result.slot}%4d: [gap=${result.gap}%2d] ⚡ FORK — $names all eligible (needs chain selection to resolve)")
    }
  }

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

    // Count blocks per staker (every eligible staker produces a block)
    val blocksByStaker = results
      .flatMap(_.eligibilities.filter(_.isEligible))
      .groupBy(_.stakerId)
      .view.mapValues(_.size).toMap

    val totalBlocks = blocksByStaker.values.sum

    // Slot gap distribution (gap to previous block-producing slot)
    val gaps = results.filter(_.eligibleCount > 0).map(_.gap)
    val avgGap    = if (gaps.nonEmpty) gaps.sum.toDouble / gaps.size else 0.0
    val medianGap = if (gaps.nonEmpty) { val s = gaps.sorted; s(s.size / 2) } else 0L
    val maxGap    = gaps.maxOption.getOrElse(0L)
    val minGap    = gaps.minOption.getOrElse(0L)
    val p99Gap    = if (gaps.nonEmpty) { val s = gaps.sorted; s((s.size * 0.99).toInt.min(s.size - 1)) } else 0L

    // Blocks per epoch
    val blocksPerEpoch = results
      .filter(_.eligibleCount > 0)
      .groupBy(_.epoch)
      .view.mapValues(_.size).toMap

    val fillRate = slotsWithBlock.toDouble / totalSlots * 100

    for {
      _ <- IO.println("")
      _ <- IO.println("=" * 60)
      _ <- IO.println("  TAKTIKOS SIMULATION SUMMARY")
      _ <- IO.println("=" * 60)
      _ <- IO.println(f"Total slots:       $totalSlots%d")
      _ <- IO.println(f"Slots with blocks: $slotsWithBlock%d ($fillRate%.1f%% fill rate)")
      _ <- IO.println(f"  Single leader:   $singleLeader%d")
      _ <- IO.println(f"  Fork (multi):    $forkSlots%d ← needs maxvalid-tk to resolve")
      _ <- IO.println(f"Empty slots:       $emptySlots%d")
      _ <- IO.println(f"Epochs:            $numEpochs%d")
      _ <- IO.println(f"Total blocks:      $totalBlocks%d (includes fork duplicates)")
      _ <- IO.println("")
      _ <- IO.println("--- Slot Gap Statistics ---")
      _ <- IO.println(f"  Mean:   $avgGap%.2f slots")
      _ <- IO.println(f"  Median: $medianGap%d slots")
      _ <- IO.println(f"  Min:    $minGap%d  Max: $maxGap%d  P99: $p99Gap%d")
      _ <- IO.println("")
      _ <- IO.println("--- Block Production by Staker (all eligibilities) ---")
      _ <- stakers.traverse_ { s =>
        val blocks     = blocksByStaker.getOrElse(s.id, 0)
        val pct        = if (totalBlocks > 0) blocks.toDouble / totalBlocks * 100 else 0.0
        val stakeRatio = s.stake.toDouble / config.totalStake * 100
        IO.println(f"  S${s.id} ($stakeRatio%.0f%% stake): $blocks%3d blocks ($pct%.1f%%)")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Blocks per Epoch (slots with ≥1 leader) ---")
      _ <- (0L until numEpochs).toList.traverse_ { e =>
        val blocks = blocksPerEpoch.getOrElse(e, 0)
        val bar    = "█" * (blocks / 2).max(1)
        IO.println(f"  Epoch $e%2d: $blocks%3d $bar")
      }
      _ <- IO.println("")
      _ <- IO.println("--- Fork Analysis ---")
      _ <- if (forkSlots > 0) {
        val forkResults = results.filter(_.isFork)
        forkResults.traverse_ { r =>
          val names = r.eligibilities.filter(_.isEligible).map(e => f"S${e.stakerId}(test=${e.testValue}%.4f)").mkString(", ")
          IO.println(f"  Slot ${r.slot}%4d [gap=${r.gap}%2d]: $names")
        }
      } else IO.println("  No forks in this run!")
      _ <- IO.println("=" * 60)
    } yield ()
  }
}
