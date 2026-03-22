package xyz.kd5ujc.signing

import java.security.MessageDigest

import cafe.cryptography.curve25519.{CompressedRistretto, Constants, Scalar}

/**
 * Ristretto255 Schnorr signature scheme.
 *
 * Operates in the prime-order ristretto255 group (order L ≈ 2^252) built
 * on Curve25519. Unlike Ed25519, ristretto eliminates the cofactor-8 complication:
 * every Scalar mod L is a valid secret key — no clamping needed.
 *
 * Scheme:
 *   - Secret key:  32-byte Scalar (reduced mod L from SHA-512(seed))
 *   - Public key:  32-byte CompressedRistretto point A = [a]G
 *   - Sign(sk, msg):
 *       r = SHA-512(noncePrefix ‖ msg) mod L        (deterministic nonce)
 *       R = [r]G
 *       c = SHA-512(R_compressed ‖ A_compressed ‖ msg) mod L
 *       s = r + c·a mod L
 *       signature = R_compressed ‖ s_bytes            (64 bytes)
 *   - Verify(sig, msg, pk):
 *       decode R, s from sig; decode A from pk
 *       c = SHA-512(R_compressed ‖ A_compressed ‖ msg) mod L
 *       check [s]G == R + [c]A
 *
 * No clamping. No cofactor multiplication. Canonical Ristretto encoding
 * guarantees unique point representation.
 *
 * Dependencies: cafe.cryptography/curve25519-elisabeth only.
 */
class Ristretto255 extends SignatureScheme[Ristretto255.SecretKey, Ristretto255.PublicKey] {

  override val seedLength: Int = Ristretto255.SeedLength

  override def deriveSecretKeyFromSeed(seed: Array[Byte]): Ristretto255.SecretKey = {
    require(
      seed.length >= Ristretto255.SeedLength,
      s"Invalid seed length. Expected >= ${Ristretto255.SeedLength}, got: ${seed.length}"
    )
    val h = sha512(seed.slice(0, Ristretto255.SeedLength))
    // Use lower 32 bytes as scalar, upper 32 as nonce prefix
    // Reduce mod L — no clamping needed for Ristretto
    val scalar = Scalar.fromBytesModOrder(h.slice(0, 32))
    val noncePrefix = h.slice(32, 64)
    Ristretto255.SecretKey(scalar.toByteArray, noncePrefix)
  }

  override def sign(privateKey: Ristretto255.SecretKey, message: Array[Byte]): Array[Byte] = {
    val a = Scalar.fromCanonicalBytes(privateKey.scalar)
    val aPoint = Constants.RISTRETTO_GENERATOR_TABLE.multiply(a)
    val aCompressed = aPoint.compress().toByteArray

    // Deterministic nonce: r = SHA-512(noncePrefix ‖ message) mod L
    val rHash = sha512(privateKey.noncePrefix, message)
    val r = Scalar.fromBytesModOrderWide(rHash)

    // R = [r]G
    val rPoint = Constants.RISTRETTO_GENERATOR_TABLE.multiply(r)
    val rCompressed = rPoint.compress().toByteArray

    // Challenge: c = SHA-512(R ‖ A ‖ message) mod L
    val cHash = sha512(rCompressed, aCompressed, message)
    val c = Scalar.fromBytesModOrderWide(cHash)

    // s = r + c * a mod L
    val s = r.add(c.multiply(a))

    // Signature = R ‖ s (64 bytes)
    val sig = new Array[Byte](Ristretto255.SignatureLength)
    System.arraycopy(rCompressed, 0, sig, 0, 32)
    System.arraycopy(s.toByteArray, 0, sig, 32, 32)
    sig
  }

  override def verify(
    signature: Array[Byte],
    message:   Array[Byte],
    publicKey: Ristretto255.PublicKey
  ): Boolean = {
    if (signature.length != Ristretto255.SignatureLength || publicKey.bytes.length != Ristretto255.PublicKeyLength)
      return false

    try {
      // Decode R
      val rCompressed = signature.slice(0, 32)
      val rPoint = new CompressedRistretto(rCompressed).decompress()

      // Decode s — must be canonical
      val sBytes = signature.slice(32, 64)
      val s = Scalar.fromCanonicalBytes(sBytes)

      // Decode A
      val aPoint = new CompressedRistretto(publicKey.bytes).decompress()

      // Challenge: c = SHA-512(R ‖ A ‖ message) mod L
      val cHash = sha512(rCompressed, publicKey.bytes, message)
      val c = Scalar.fromBytesModOrderWide(cHash)

      // Check: [s]G == R + [c]A
      val lhs = Constants.RISTRETTO_GENERATOR_TABLE.multiply(s)
      val rhs = rPoint.add(aPoint.multiply(c))

      lhs.equals(rhs)
    } catch {
      case _: Exception => false
    }
  }

  override def getVerificationKey(privateKey: Ristretto255.SecretKey): Ristretto255.PublicKey = {
    val a = Scalar.fromCanonicalBytes(privateKey.scalar)
    val aPoint = Constants.RISTRETTO_GENERATOR_TABLE.multiply(a)
    Ristretto255.PublicKey(aPoint.compress().toByteArray)
  }

  // --- SHA-512 helpers ---

  private def sha512(input: Array[Byte]): Array[Byte] =
    MessageDigest.getInstance("SHA-512").digest(input)

  private def sha512(a: Array[Byte], b: Array[Byte]): Array[Byte] = {
    val md = MessageDigest.getInstance("SHA-512")
    md.update(a)
    md.update(b)
    md.digest()
  }

  private def sha512(a: Array[Byte], b: Array[Byte], c: Array[Byte]): Array[Byte] = {
    val md = MessageDigest.getInstance("SHA-512")
    md.update(a)
    md.update(b)
    md.update(c)
    md.digest()
  }
}

object Ristretto255 {
  val SignatureLength: Int = 64
  val ScalarLength: Int = 32
  val PublicKeyLength: Int = 32
  val SeedLength: Int = 32

  /**
   * Secret key = reduced scalar (32 bytes) + nonce prefix (32 bytes).
   *
   * Unlike Ed25519, the scalar is simply reduced mod L — no bit clamping.
   */
  case class SecretKey(scalar: Array[Byte], noncePrefix: Array[Byte]) extends SigningKey {
    require(scalar.length == ScalarLength, s"Invalid scalar length. Expected: $ScalarLength, got: ${scalar.length}")
    require(
      noncePrefix.length == ScalarLength,
      s"Invalid nonce prefix length. Expected: $ScalarLength, got: ${noncePrefix.length}"
    )

    override def bytes: Array[Byte] = scalar ++ noncePrefix

    override def equals(obj: Any): Boolean = obj match {
      case that: SecretKey =>
        java.util.Arrays.equals(this.scalar, that.scalar) &&
        java.util.Arrays.equals(this.noncePrefix, that.noncePrefix)
      case _ => false
    }
    override def hashCode(): Int =
      java.util.Arrays.hashCode(scalar) * 31 + java.util.Arrays.hashCode(noncePrefix)
  }

  case class PublicKey(bytes: Array[Byte]) extends VerificationKey {
    require(
      bytes.length == PublicKeyLength,
      s"Invalid public key length. Expected: $PublicKeyLength, got: ${bytes.length}"
    )

    override def equals(obj: Any): Boolean = obj match {
      case that: PublicKey => java.util.Arrays.equals(this.bytes, that.bytes)
      case _               => false
    }
    override def hashCode(): Int = java.util.Arrays.hashCode(bytes)
  }
}
