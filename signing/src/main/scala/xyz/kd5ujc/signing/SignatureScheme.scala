package xyz.kd5ujc.signing

/**
 * Abstract signature scheme parameterized by key types.
 */
trait SignatureScheme[SK <: SigningKey, VK <: VerificationKey] {

  /** Seed size in bytes for key derivation */
  def seedLength: Int

  /** Derive a secret key from a seed */
  def deriveSecretKeyFromSeed(seed: Array[Byte]): SK

  /** Derive a key pair from a seed */
  def deriveKeyPairFromSeed(seed: Array[Byte]): KeyPair[SK, VK] = {
    val sk = deriveSecretKeyFromSeed(seed)
    val vk = getVerificationKey(sk)
    KeyPair(sk, vk)
  }

  /** Sign a message */
  def sign(privateKey: SK, message: Array[Byte]): Array[Byte]

  /** Verify a signature */
  def verify(signature: Array[Byte], message: Array[Byte], publicKey: VK): Boolean

  /** Get the public key from a private key */
  def getVerificationKey(privateKey: SK): VK
}
