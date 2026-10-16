package org.bakasu.bakasu.data.shell

import java.io.File
import java.security.MessageDigest
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ManagerSignatureTest {
    private val certificate = File(requireNotNull(System.getProperty("managerCertificateFile"))).readBytes()

    private fun signatureOutput(bytes: ByteArray): String {
        val hash = MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
        return "size: 0x${bytes.size.toString(16)}, hash: $hash"
    }

    @Test
    fun acceptsPrivateCertificateUsedByGkiAndLkm() {
        assertTrue(isExpectedManagerSignature(true, listOf(signatureOutput(certificate))))
    }

    @Test
    fun rejectsUpstreamCertificate() {
        assertFalse(
            isExpectedManagerSignature(
                true,
                listOf("size: 0x377, hash: d3469712b6214462764a1d8d3e5cbe1d6819a0b629791b9f4101867821f1df64"),
            ),
        )
    }

    @Test
    fun rejectsChangedCertificate() {
        val changed = certificate.copyOf()
        changed[changed.lastIndex] = (changed.last().toInt() xor 1).toByte()
        assertFalse(isExpectedManagerSignature(true, listOf(signatureOutput(changed))))
    }

    @Test
    fun rejectsWrongCertificateSize() {
        val wrongSize = signatureOutput(certificate).replace(
            "size: 0x${certificate.size.toString(16)}",
            "size: 0x${(certificate.size + 1).toString(16)}",
        )
        assertFalse(isExpectedManagerSignature(true, listOf(wrongSize)))
    }

    @Test
    fun rejectsFailedOrAmbiguousCheck() {
        val valid = signatureOutput(certificate)
        assertFalse(isExpectedManagerSignature(false, listOf(valid)))
        assertFalse(isExpectedManagerSignature(true, emptyList()))
        assertFalse(isExpectedManagerSignature(true, listOf("invalid")))
        assertFalse(isExpectedManagerSignature(true, listOf(valid, valid)))
    }
}
