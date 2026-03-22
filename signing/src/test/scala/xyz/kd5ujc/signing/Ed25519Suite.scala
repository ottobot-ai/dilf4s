package xyz.kd5ujc.signing

import java.util.HexFormat

import cats.effect.IO

import io.circe.generic.auto._
import io.circe.parser
import weaver.SimpleIOSuite

object Ed25519Suite extends SimpleIOSuite {

  private val hex = HexFormat.of()
  private val ed25519 = new Ed25519()

  // Load test vectors
  case class TestInputs(secretKey: String, message: String)
  case class TestOutputs(verificationKey: String, signature: String)
  case class TestVector(description: String, inputs: TestInputs, outputs: TestOutputs)

  private val vectors: List[TestVector] = {
    val source = scala.io.Source.fromFile("docs/test-vectors/Ed25519.json")
    val json =
      try source.mkString
      finally source.close()
    parser.decode[List[TestVector]](json).getOrElse(throw new RuntimeException("Failed to parse test vectors"))
  }

  // Generate a test for each vector
  vectors.foreach { vector =>
    test(s"Ed25519 - ${vector.description} - derive verification key") {
      IO {
        val sk = Ed25519.SecretKey(hex.parseHex(vector.inputs.secretKey))
        val expectedVk = hex.parseHex(vector.outputs.verificationKey)
        val actualVk = ed25519.getVerificationKey(sk)
        expect(java.util.Arrays.equals(actualVk.bytes, expectedVk))
      }
    }

    test(s"Ed25519 - ${vector.description} - sign") {
      IO {
        val sk = Ed25519.SecretKey(hex.parseHex(vector.inputs.secretKey))
        val message = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val expectedSig = hex.parseHex(vector.outputs.signature)
        val actualSig = ed25519.sign(sk, message)
        expect(java.util.Arrays.equals(actualSig, expectedSig))
      }
    }

    test(s"Ed25519 - ${vector.description} - verify") {
      IO {
        val vk = Ed25519.PublicKey(hex.parseHex(vector.outputs.verificationKey))
        val message = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val signature = hex.parseHex(vector.outputs.signature)
        expect(ed25519.verify(signature, message, vk))
      }
    }

    test(s"Ed25519 - ${vector.description} - reject tampered signature") {
      IO {
        val vk = Ed25519.PublicKey(hex.parseHex(vector.outputs.verificationKey))
        val message = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val signature = hex.parseHex(vector.outputs.signature)
        val tampered = signature.clone()
        tampered(0) = (tampered(0) ^ 0xff).toByte
        expect(!ed25519.verify(tampered, message, vk))
      }
    }
  }

  // Additional property tests
  test("Ed25519 - roundtrip: sign then verify") {
    IO {
      val seed = new Array[Byte](32)
      new java.security.SecureRandom().nextBytes(seed)
      val kp = ed25519.deriveKeyPairFromSeed(seed)
      val message = "Hello, World!".getBytes("UTF-8")
      val sig = ed25519.sign(kp.signingKey, message)
      expect(ed25519.verify(sig, message, kp.verificationKey))
    }
  }

  test("Ed25519 - wrong message fails verification") {
    IO {
      val seed = new Array[Byte](32)
      new java.security.SecureRandom().nextBytes(seed)
      val kp = ed25519.deriveKeyPairFromSeed(seed)
      val message = "Hello, World!".getBytes("UTF-8")
      val sig = ed25519.sign(kp.signingKey, message)
      val wrongMessage = "Wrong message".getBytes("UTF-8")
      expect(!ed25519.verify(sig, wrongMessage, kp.verificationKey))
    }
  }

  test("Ed25519 - wrong key fails verification") {
    IO {
      val seed1 = new Array[Byte](32)
      val seed2 = new Array[Byte](32)
      val rng = new java.security.SecureRandom()
      rng.nextBytes(seed1)
      rng.nextBytes(seed2)
      val kp1 = ed25519.deriveKeyPairFromSeed(seed1)
      val kp2 = ed25519.deriveKeyPairFromSeed(seed2)
      val message = "Hello, World!".getBytes("UTF-8")
      val sig = ed25519.sign(kp1.signingKey, message)
      expect(!ed25519.verify(sig, message, kp2.verificationKey))
    }
  }
}
