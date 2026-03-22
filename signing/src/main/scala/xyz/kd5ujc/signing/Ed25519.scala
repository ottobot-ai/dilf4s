package xyz.kd5ujc.signing

import java.security.MessageDigest

/**
 * Standard Ed25519 signature scheme (RFC 8032 §5.1).
 *
 * Key expansion: SHA-512(seed) → lower 32 bytes clamped = scalar, upper 32 = nonce prefix.
 * Signing and verification delegate to [[Ed25519Signing]].
 *
 * Dependencies: curve25519-elisabeth only (no ed25519-elisabeth).
 */
class Ed25519 extends SignatureScheme[Ed25519.SecretKey, Ed25519.PublicKey] {

  override val seedLength: Int = Ed25519.SeedLength

  override def deriveSecretKeyFromSeed(seed: Array[Byte]): Ed25519.SecretKey = {
    require(
      seed.length >= Ed25519.SeedLength,
      s"Invalid seed length. Expected >= ${Ed25519.SeedLength}, got: ${seed.length}"
    )
    Ed25519.SecretKey(seed.slice(0, Ed25519.SeedLength))
  }

  override def sign(privateKey: Ed25519.SecretKey, message: Array[Byte]): Array[Byte] = {
    val (scalar, noncePrefix) = expand(privateKey.bytes)
    val pk = Ed25519Signing.publicKeyFromScalar(scalar)
    Ed25519Signing.sign(scalar, noncePrefix, pk, message)
  }

  override def verify(
    signature: Array[Byte],
    message:   Array[Byte],
    publicKey: Ed25519.PublicKey
  ): Boolean =
    Ed25519Signing.verify(signature, message, publicKey.bytes)

  override def getVerificationKey(privateKey: Ed25519.SecretKey): Ed25519.PublicKey = {
    val (scalar, _) = expand(privateKey.bytes)
    Ed25519.PublicKey(Ed25519Signing.publicKeyFromScalar(scalar))
  }

  /**
   * Expand a 32-byte seed into (scalar, noncePrefix) per RFC 8032 §5.1.5.
   *
   * SHA-512(seed) → h[0..32] clamped = scalar, h[32..64] = nonce prefix.
   */
  private def expand(seed: Array[Byte]): (Array[Byte], Array[Byte]) = {
    val h = MessageDigest.getInstance("SHA-512").digest(seed)
    val scalar = h.slice(0, 32)

    // Clamp per RFC 8032 §5.1.5
    scalar(0) = (scalar(0) & 0xf8).toByte
    scalar(31) = (scalar(31) & 0x7f).toByte
    scalar(31) = (scalar(31) | 0x40).toByte

    val noncePrefix = h.slice(32, 64)
    (scalar, noncePrefix)
  }
}

object Ed25519 {
  val SignatureLength: Int = 64
  val KeyLength: Int = 32
  val PublicKeyLength: Int = 32
  val SeedLength: Int = 32

  case class SecretKey(bytes: Array[Byte]) extends SigningKey {
    require(bytes.length == KeyLength, s"Invalid secret key length. Expected: $KeyLength, got: ${bytes.length}")

    override def equals(obj: Any): Boolean = obj match {
      case that: SecretKey => java.util.Arrays.equals(this.bytes, that.bytes)
      case _               => false
    }
    override def hashCode(): Int = java.util.Arrays.hashCode(bytes)
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
