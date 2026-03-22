package xyz.kd5ujc.taktikos

import java.security.SecureRandom

import cats.effect.{IO, IOApp, Ref}
import cats.implicits._

/**
 * Taktikos leader election simulation.
 *
 * Simulates the PoS leader election from Bifrost/Topl where each staker
 * checks every slot whether they're eligible to produce a block using
 * a VRF + threshold mechanism (Local Dynamic Difficulty).
 */
object TaktikosSimulation extends IOApp.Simple {

  val config: SimulationConfig = SimulationConfig(
    numStakers = 5,
    totalSlots = 100,
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
      // Initialize stakers with random VRF keys and assigned stake
      stakers <- initializeStakers(config)

      // Genesis eta - Blake2b-256 of seed string
      eta = Eta(LeaderElection.blake2b256("taktikos-genesis-eta".getBytes("UTF-8")))

      // Print header
      _ <- IO.println(
        s"Starting Taktikos simulation with ${config.numStakers} stakers over ${config.totalSlots} slots"
      )
      _ <- IO.println(s"Stake distribution: ${stakers.map(s => s"Staker${s.id}=${s.stake}").mkString(", ")}")
      _ <- IO.println(
        s"VRF Config: lddCutoff=${config.vrfConfig.lddCutoff}, " +
        s"baselineDifficulty=${config.vrfConfig.baselineDifficulty}, " +
        s"amplitude=${config.vrfConfig.amplitude}"
      )
      _ <- IO.println("---")

      // Run simulation
      results <- simulateSlots(stakers, config, eta)

      // Print summary
      _ <- printSummary(results, stakers, config)
    } yield ()

  /**
   * Initialize stakers with random VRF keys and pre-defined stake distribution.
   */
  def initializeStakers(config: SimulationConfig): IO[List[Staker]] = IO {
    val random = new SecureRandom()

    (0 until config.numStakers).toList.map { id =>
      val sk = new Array[Byte](32)
      random.nextBytes(sk)
      val vk    = LeaderElection.deriveVrfVK(sk)
      val stake = stakeDistribution(id)
      Staker(id, sk, vk, stake)
    }
  }

  /**
   * Simulate all slots and collect results.
   */
  def simulateSlots(
    stakers: List[Staker],
    config:  SimulationConfig,
    eta:     Eta
  ): IO[List[SlotResult]] =
    for {
      // Track last block slot for LDD calculation (start at 0 = genesis)
      lastBlockSlotRef <- Ref.of[IO, Long](0L)
      results <- (1L to config.totalSlots).toList.traverse { slot =>
        for {
          lastBlockSlot <- lastBlockSlotRef.get
          slotDiff       = slot - lastBlockSlot

          // Check eligibility for all stakers
          eligibilities = stakers.map { staker =>
            LeaderElection.checkEligibility(
              staker,
              slot,
              slotDiff,
              eta,
              config.totalStake,
              config.vrfConfig
            )
          }

          eligibleStakers = eligibilities.filter(_.isEligible)
          result          = SlotResult(slot, slotDiff, eligibleStakers.size, eligibilities)

          // If any staker elected, update lastBlockSlot
          _ <- if (eligibleStakers.nonEmpty) lastBlockSlotRef.set(slot) else IO.unit

          // Print slot result
          _ <- printSlotResult(result)
        } yield result
      }
    } yield results

  /**
   * Print result for a single slot.
   */
  def printSlotResult(result: SlotResult): IO[Unit] = {
    val slotStr = f"Slot ${result.slot}%3d"
    val gapStr  = f"[gap=${result.gap}%2d]"

    val eligible = result.eligibilities.filter(_.isEligible)

    val msg = eligible match {
      case Nil =>
        val maxThreshold = result.eligibilities.map(_.threshold).maxOption.getOrElse(0.0)
        f"No leader (max threshold: $maxThreshold%.4f)"

      case single :: Nil =>
        f"Staker${single.stakerId} ELECTED (threshold=${single.threshold}%.4f, " +
        f"test=${single.testValue}%.4f, stake=${single.stakePercent}%.1f%%)"

      case multiple =>
        multiple.map { e =>
          f"Staker${e.stakerId}"
        }.mkString(", ") + " (fork potential!)"
    }

    IO.println(s"$slotStr: $gapStr $msg")
  }

  /**
   * Print final summary statistics.
   */
  def printSummary(
    results: List[SlotResult],
    stakers: List[Staker],
    config:  SimulationConfig
  ): IO[Unit] = {
    val blocksProduced = results.count(_.eligibleCount > 0)
    val emptySlots     = results.count(_.eligibleCount == 0)
    val multiLeader    = results.count(_.eligibleCount > 1)

    // Count blocks per staker (using first eligible when multiple)
    val blocksByStaker = results
      .flatMap(_.eligibilities.filter(_.isEligible).headOption)
      .groupBy(_.stakerId)
      .view
      .mapValues(_.size)
      .toMap

    // Calculate average gap between blocks
    val gaps = results.filter(_.eligibleCount > 0).map(_.gap)
    val avgGap = if (gaps.nonEmpty) gaps.sum.toDouble / gaps.size else 0.0

    for {
      _ <- IO.println("")
      _ <- IO.println("=== SUMMARY ===")
      _ <- IO.println(s"Total slots: ${config.totalSlots}")
      _ <- IO.println(s"Blocks produced: $blocksProduced")
      _ <- IO.println(s"Empty slots: $emptySlots")
      _ <- stakers.traverse_ { s =>
        val blocks     = blocksByStaker.getOrElse(s.id, 0)
        val pct        = if (blocksProduced > 0) blocks.toDouble / blocksProduced * 100 else 0.0
        val stakeRatio = s.stake.toDouble / config.totalStake * 100
        IO.println(f"Staker${s.id} ($stakeRatio%.1f%% stake): $blocks%2d blocks ($pct%.1f%%)")
      }
      _ <- IO.println(s"Multi-leader slots: $multiLeader (fork potential)")
      _ <- IO.println(f"Average slot gap between blocks: $avgGap%.2f")
    } yield ()
  }
}
