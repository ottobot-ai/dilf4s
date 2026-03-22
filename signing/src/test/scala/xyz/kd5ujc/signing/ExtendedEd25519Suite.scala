package xyz.kd5ujc.signing

import java.util.HexFormat

import cats.effect.IO
import io.circe.generic.auto._
import io.circe.parser
import weaver.SimpleIOSuite

object ExtendedEd25519Suite extends SimpleIOSuite {

  private val hex        = HexFormat.of()
  private val extEd25519 = new ExtendedEd25519()
  private val ed25519    = new Ed25519()

  case class TestInputs(secretKey: String, message: String)
  case class TestOutputs(verificationKey: String, signature: String)
  case class TestVector(description: String, inputs: TestInputs, outputs: TestOutputs)

  private val vectors: List[TestVector] = {
    val source = scala.io.Source.fromFile("docs/test-vectors/ExtendedEd25519.json")
    val json   = try source.mkString finally source.close()
    parser.decode[List[TestVector]](json).getOrElse(throw new RuntimeException("Failed to parse test vectors"))
  }

  vectors.foreach { vector =>
    test(s"ExtendedEd25519 - ${vector.description} - derive verification key") {
      IO {
        val skBytes = hex.parseHex(vector.inputs.secretKey)
        val sk = ExtendedEd25519.SecretKey(
          skBytes.slice(0, 32),
          skBytes.slice(32, 64),
          skBytes.slice(64, 96)
        )
        val expectedVkBytes = hex.parseHex(vector.outputs.verificationKey)
        val expectedPk      = expectedVkBytes.slice(0, 32)
        val expectedCC      = expectedVkBytes.slice(32, 64)
        val actualVk        = extEd25519.getVerificationKey(sk)
        expect(java.util.Arrays.equals(actualVk.vk.bytes, expectedPk)) and
        expect(java.util.Arrays.equals(actualVk.chainCode, expectedCC))
      }
    }

    test(s"ExtendedEd25519 - ${vector.description} - sign and verify roundtrip") {
      IO {
        val skBytes = hex.parseHex(vector.inputs.secretKey)
        val sk = ExtendedEd25519.SecretKey(
          skBytes.slice(0, 32),
          skBytes.slice(32, 64),
          skBytes.slice(64, 96)
        )
        val message   = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val actualVk  = extEd25519.getVerificationKey(sk)
        val actualSig = extEd25519.sign(sk, message)
        // Verify our signature works with our derived vk
        expect(extEd25519.verify(actualSig, message, actualVk))
      }
    }

    test(s"ExtendedEd25519 - ${vector.description} - verify expected signature") {
      IO {
        val skBytes = hex.parseHex(vector.inputs.secretKey)
        val sk = ExtendedEd25519.SecretKey(
          skBytes.slice(0, 32),
          skBytes.slice(32, 64),
          skBytes.slice(64, 96)
        )
        val message     = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val expectedSig = hex.parseHex(vector.outputs.signature)
        val vkBytes     = hex.parseHex(vector.outputs.verificationKey)
        val expectedVk  = ExtendedEd25519.PublicKey(Ed25519.PublicKey(vkBytes.slice(0, 32)), vkBytes.slice(32, 64))
        // Verify expected signature with expected vk
        expect(extEd25519.verify(expectedSig, message, expectedVk))
      }
    }

    test(s"ExtendedEd25519 - ${vector.description} - verify with Ed25519") {
      IO {
        val vkBytes   = hex.parseHex(vector.outputs.verificationKey)
        val vk        = Ed25519.PublicKey(vkBytes.slice(0, 32))
        val message   = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val signature = hex.parseHex(vector.outputs.signature)
        expect(ed25519.verify(signature, message, vk))
      }
    }

    test(s"ExtendedEd25519 - ${vector.description} - reject tampered") {
      IO {
        val vkBytes   = hex.parseHex(vector.outputs.verificationKey)
        val vk        = ExtendedEd25519.PublicKey(Ed25519.PublicKey(vkBytes.slice(0, 32)), vkBytes.slice(32, 64))
        val message   = if (vector.inputs.message.isEmpty) Array.emptyByteArray else hex.parseHex(vector.inputs.message)
        val signature = hex.parseHex(vector.outputs.signature)
        val tampered  = signature.clone()
        tampered(0) = (tampered(0) ^ 0xff).toByte
        expect(!extEd25519.verify(tampered, message, vk))
      }
    }
  }

  // Roundtrip
  test("ExtendedEd25519 - roundtrip: sign then verify") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp      = extEd25519.deriveKeyPairFromSeed(seed)
      val message = "Hello, World!".getBytes("UTF-8")
      val sig     = extEd25519.sign(kp.signingKey, message)
      expect(extEd25519.verify(sig, message, kp.verificationKey))
    }
  }

  // Cross-verify with standard Ed25519
  test("ExtendedEd25519 - signatures verifiable by standard Ed25519") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp      = extEd25519.deriveKeyPairFromSeed(seed)
      val message = "Cross verify test".getBytes("UTF-8")
      val sig     = extEd25519.sign(kp.signingKey, message)
      // Standard Ed25519 should verify the same signature with the raw 32-byte public key
      expect(ed25519.verify(sig, message, kp.verificationKey.vk))
    }
  }

  // Child key derivation
  test("ExtendedEd25519 - child key derivation: soft index produces valid keys") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp      = extEd25519.deriveKeyPairFromSeed(seed)
      val childSk = extEd25519.deriveChildSecretKey(kp.signingKey, Bip32Index.soft(0))
      val childVk = extEd25519.getVerificationKey(childSk)
      val message = "child key test".getBytes("UTF-8")
      val sig     = extEd25519.sign(childSk, message)
      expect(extEd25519.verify(sig, message, ExtendedEd25519.PublicKey(childVk.vk, childVk.chainCode)))
    }
  }

  // Public child derivation matches secret child derivation (soft indices only)
  test("ExtendedEd25519 - soft child: public derivation matches secret derivation") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp  = extEd25519.deriveKeyPairFromSeed(seed)
      val idx = Bip32Index.soft(42)

      val childFromSk = extEd25519.deriveChildSecretKey(kp.signingKey, idx)
      val vkFromSk    = extEd25519.getVerificationKey(childFromSk)

      val vkFromPub = extEd25519.deriveChildVerificationKey(kp.verificationKey, idx.asInstanceOf[Bip32Index.SoftIndex])

      expect(java.util.Arrays.equals(vkFromSk.vk.bytes, vkFromPub.vk.bytes)) and
      expect(java.util.Arrays.equals(vkFromSk.chainCode, vkFromPub.chainCode))
    }
  }

  // Hardened child key
  test("ExtendedEd25519 - hardened child key derivation produces valid keys") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp      = extEd25519.deriveKeyPairFromSeed(seed)
      val childSk = extEd25519.deriveChildSecretKey(kp.signingKey, Bip32Index.hardened(0))
      val childVk = extEd25519.getVerificationKey(childSk)
      val message = "hardened child test".getBytes("UTF-8")
      val sig     = extEd25519.sign(childSk, message)
      expect(extEd25519.verify(sig, message, ExtendedEd25519.PublicKey(childVk.vk, childVk.chainCode)))
    }
  }

  // Different soft indices produce different keys
  test("ExtendedEd25519 - different indices produce different child keys") {
    IO {
      val seed = new Array[Byte](96)
      new java.security.SecureRandom().nextBytes(seed)
      val kp     = extEd25519.deriveKeyPairFromSeed(seed)
      val child0 = extEd25519.deriveChildSecretKey(kp.signingKey, Bip32Index.soft(0))
      val child1 = extEd25519.deriveChildSecretKey(kp.signingKey, Bip32Index.soft(1))
      expect(!java.util.Arrays.equals(child0.leftKey, child1.leftKey))
    }
  }
}
