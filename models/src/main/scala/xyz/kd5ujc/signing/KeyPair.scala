package xyz.kd5ujc.signing

/** A key pair */
case class KeyPair[SK <: SigningKey, VK <: VerificationKey](signingKey: SK, verificationKey: VK)
