package xyz.kd5ujc.signing

import java.security.MessageDigest

import cafe.cryptography.curve25519.{CompressedEdwardsY, Constants, EdwardsPoint, Scalar}

/**
 * Shared Ed25519 signing core using curve25519-elisabeth primitives.
 *
 * Both Ed25519 and ExtendedEd25519 produce signatures via the same
 * RFC 8032 §5.1 algorithm — only the key expansion step differs.
 * This object provides the common sign/verify/getPublicKey operations
 * so neither scheme needs to reimplement them.
 *
 * Dependencies: cafe.cryptography/curve25519-elisabeth only (no ed25519-elisabeth).
 */
object Ed25519Signing {

  val ScalarBytes: Int    = 32
  val PointBytes: Int     = 32
  val SignatureBytes: Int = 64

  /**
   * Sign a message given a pre-expanded key.
   *
   * @param scalar      32-byte scalar (leftKey for extended, pruned hash for standard)
   * @param noncePrefix 32-byte nonce prefix (rightKey for extended, upper hash for standard)
   * @param publicKey   32-byte compressed public key
   * @param message     the message to sign
   * @return 64-byte signature (R ++ S)
   */
  def sign(
    scalar:      Array[Byte],
    noncePrefix: Array[Byte],
    publicKey:   Array[Byte],
    message:     Array[Byte]
  ): Array[Byte] = {
    // r = SHA-512(noncePrefix || message) mod L
    val rHash = sha512(noncePrefix, message)
    val r     = Scalar.fromBytesModOrderWide(rHash)

    // R = r * B
    val rPoint  = Constants.ED25519_BASEPOINT_TABLE.multiply(r)
    val encodedR = rPoint.compress().toByteArray

    // k = SHA-512(R || publicKey || message) mod L
    val kHash = sha512(encodedR, publicKey, message)
    val k     = Scalar.fromBytesModOrderWide(kHash)

    // S = r + k * s mod L
    // Load scalar via fromBytesModOrderWide to properly handle all 256 bits.
    // For standard Ed25519, the clamped scalar has bit255=0 so this is identity.
    // For extended Ed25519, the leftKey may use all bits.
    val s      = scalarFromBytes(scalar)
    val sValue = r.add(k.multiply(s))

    // signature = R || S
    val sig = new Array[Byte](SignatureBytes)
    System.arraycopy(encodedR, 0, sig, 0, PointBytes)
    System.arraycopy(sValue.toByteArray, 0, sig, PointBytes, ScalarBytes)
    sig
  }

  /**
   * Verify a signature against a message and public key.
   *
   * Uses the standard Ed25519 verification equation:
   *   [8][S]B = [8]R + [8][k]A
   *
   * @param signature 64-byte signature
   * @param message   the message
   * @param publicKey 32-byte compressed public key
   * @return true if valid
   */
  def verify(
    signature: Array[Byte],
    message:   Array[Byte],
    publicKey: Array[Byte]
  ): Boolean = {
    if (signature.length != SignatureBytes || publicKey.length != PointBytes)
      return false

    try {
      // Decode R (first 32 bytes)
      val encodedR = signature.slice(0, PointBytes)

      // Decode S (last 32 bytes) — must be canonical
      val sBytes = signature.slice(PointBytes, SignatureBytes)
      val s      = Scalar.fromCanonicalBytes(sBytes)

      // Decode public key A
      val aPoint = new CompressedEdwardsY(publicKey).decompress()

      // k = SHA-512(R || A || message)
      val kHash = sha512(encodedR, publicKey, message)
      val k     = Scalar.fromBytesModOrderWide(kHash)

      // Check: [S]B == R + [k]A
      // Rearranged: [-k]A + [S]B == R
      // vartimeDoubleScalarMultiplyBasepoint(a, A, b) computes [a]A + [b]B
      val kNeg   = Scalar.ZERO.subtract(k)
      val result = EdwardsPoint.vartimeDoubleScalarMultiplyBasepoint(kNeg, aPoint, s)

      // Compare compressed forms
      result.compress().toByteArray.sameElements(encodedR)
    } catch {
      case _: Exception => false
    }
  }

  /**
   * Derive the 32-byte compressed public key from a scalar.
   *
   * @param scalar 32-byte scalar
   * @return 32-byte compressed Edwards Y encoding
   */
  def publicKeyFromScalar(scalar: Array[Byte]): Array[Byte] = {
    val s = scalarFromBytes(scalar)
    Constants.ED25519_BASEPOINT_TABLE.multiply(s).compress().toByteArray
  }

  /**
   * Load a 32-byte scalar, reducing mod L.
   *
   * Uses fromBytesModOrderWide with zero-padding so all 256 bits are
   * properly reduced. This handles both clamped Ed25519 scalars (where
   * bit 255 is already 0) and ExtendedEd25519 leftKeys (which may
   * use the full range).
   */
  private def scalarFromBytes(bytes: Array[Byte]): Scalar = {
    val padded = new Array[Byte](64)
    System.arraycopy(bytes, 0, padded, 0, 32)
    Scalar.fromBytesModOrderWide(padded)
  }

  // --- SHA-512 helpers ---

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
