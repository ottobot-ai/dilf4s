package xyz.kd5ujc.kes

/**
 * Public API for KES Product Composition.
 *
 * Product composition nests a "super" sum tree over "sub" sum trees.
 * Heights (h_sup, h_sub) yields 2^(h_sup + h_sub) time steps.
 */
class KesProduct extends ProductComposition {

  /**
   * Create a new KES product keypair.
   *
   * @param seed   32-byte input entropy
   * @param height (super height, sub height)
   * @return (secret key, verification key)
   */
  def createKeyPair(
    seed:   Array[Byte],
    height: (Int, Int)
  ): (SecretKeyKesProduct, VerificationKeyKesProduct) = {
    val sk = generateSecretKey(seed.clone(), height._1, height._2)
    val pk = generateVerificationKey(sk)
    (
      SecretKeyKesProduct(
        sk._1,
        sk._2,
        sk._3,
        SignatureKesSum(sk._4._1, sk._4._2, sk._4._3)
      ),
      VerificationKeyKesProduct(pk._1, pk._2)
    )
  }

  /**
   * Sign a message with the KES product secret key.
   *
   * @param privateKey secret key
   * @param message    message to sign
   * @return KES product signature
   */
  def sign(privateKey: SecretKeyKesProduct, message: Array[Byte]): SignatureKesProduct = {
    val prodSig = sign(unpackSecret(privateKey), message)
    SignatureKesProduct(
      SignatureKesSum(prodSig._1._1, prodSig._1._2, prodSig._1._3),
      SignatureKesSum(prodSig._2._1, prodSig._2._2, prodSig._2._3),
      prodSig._3
    )
  }

  /**
   * Verify a KES product signature.
   *
   * @param signature signature to verify
   * @param message   message that was signed
   * @param verifyKey verification key
   * @return true if valid
   */
  def verify(
    signature: SignatureKesProduct,
    message:   Array[Byte],
    verifyKey: VerificationKeyKesProduct
  ): Boolean = {
    val prodSig = (
      (
        signature.superSignature.verificationKey,
        signature.superSignature.signature,
        signature.superSignature.witness.toVector
      ),
      (
        signature.subSignature.verificationKey,
        signature.subSignature.signature,
        signature.subSignature.witness.toVector
      ),
      signature.subRoot
    )
    val sumVk = (verifyKey.value, verifyKey.step)
    verify(prodSig, message, sumVk)
  }

  /**
   * Update the secret key to a new time step.
   *
   * @param privateKey current secret key
   * @param steps      target time step
   * @return updated secret key
   */
  def update(privateKey: SecretKeyKesProduct, steps: Int): SecretKeyKesProduct = {
    val sk = updateKey(unpackSecret(privateKey), steps)
    SecretKeyKesProduct(
      sk._1,
      sk._2,
      sk._3,
      SignatureKesSum(sk._4._1, sk._4._2, sk._4._3)
    )
  }

  /**
   * Get the current time step of a secret key.
   */
  def getCurrentStep(privateKey: SecretKeyKesProduct): Int =
    getKeyTime(unpackSecret(privateKey))

  /**
   * Get the maximum time step for a secret key.
   */
  def getMaxStep(privateKey: SecretKeyKesProduct): Int =
    exp(getTreeHeight(privateKey.superTree) + getTreeHeight(privateKey.subTree))

  /**
   * Derive the verification key from a secret key.
   */
  def getVerificationKey(privateKey: SecretKeyKesProduct): VerificationKeyKesProduct = {
    val vk = generateVerificationKey(unpackSecret(privateKey))
    VerificationKeyKesProduct(vk._1, vk._2)
  }

  private def unpackSecret(privateKey: SecretKeyKesProduct): SK =
    (
      privateKey.superTree,
      privateKey.subTree,
      privateKey.nextSubSeed,
      (
        privateKey.subSignature.verificationKey,
        privateKey.subSignature.signature,
        privateKey.subSignature.witness.toVector
      )
    )
}

object KesProduct {
  val instance: KesProduct = new KesProduct
}
