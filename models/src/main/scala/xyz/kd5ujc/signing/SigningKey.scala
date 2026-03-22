package xyz.kd5ujc.signing

/** Marker trait for signing keys */
trait SigningKey {
  def bytes: Array[Byte]

  override def equals(obj: Any): Boolean = obj match {
    case that: SigningKey => java.util.Arrays.equals(this.bytes, that.bytes)
    case _                => false
  }

  override def hashCode(): Int = java.util.Arrays.hashCode(bytes)
}
