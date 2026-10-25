package org.bakasu.bakasu.data.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ManagerUpdateSourceTest {
    @Test
    fun stableUpdatesUseTheProRepository() {
        assertEquals(
            "https://api.github.com/repos/vring99/BakaSU/releases/latest",
            ManagerUpdateSource.stableUrl,
        )
    }

    @Test
    fun betaUpdatesIncludeManualBuildsOnTheProBranch() {
        assertEquals(
            "https://api.github.com/repos/vring99/BakaSU/actions/workflows/" +
                "build-private-manager.yml/runs?branch=codex%2Fbuild-35233&status=success&per_page=1",
            ManagerUpdateSource.betaRunsUrl,
        )
    }

    @Test
    fun betaDownloadsUseTheFinalRepackedArtifact() {
        assertEquals(
            "https://nightly.link/vring99/BakaSU/actions/runs/40077253447/BakaSU-Pro-release.zip",
            ManagerUpdateSource.artifactUrl(40077253447L),
        )
    }

    @Test
    fun versionChecksUseTheSameRepository() {
        assertEquals(
            "https://api.github.com/repos/vring99/BakaSU/commits?sha=cc2e4f766b2ee411&per_page=1",
            ManagerUpdateSource.commitsUrl("cc2e4f766b2ee411"),
        )
    }

    @Test
    fun acceptsEveryProReleaseArchitecture() {
        for (abi in listOf("arm64-v8a", "armeabi-v7a", "x86_64", "riscv64", "universal")) {
            val fileName = "BakaSU_Pro_v4.2.0-rc3_35243-$abi-release.apk"
            val parsed = requireNotNull(ManagerUpdateSource.parseApkName(fileName))
            assertEquals("v4.2.0-rc3", parsed.versionName)
            assertEquals(35243, parsed.versionCode)
            assertEquals(abi, parsed.abi)
            assertEquals(fileName, parsed.fileName)
        }
    }

    @Test
    fun ignoresOfficialDebugAndMalformedApks() {
        for (fileName in listOf(
            "BakaSU_v4.2.0-rc3_35244-arm64-v8a-release.apk",
            "BakaSU_Pro_v4.2.0-rc3_35244-arm64-v8a-debug.apk",
            "BakaSU_Pro_v4.2.0-rc3_35244-mips-release.apk",
            "BakaSU_Pro_v4.2.0-rc3_9999999999999999-arm64-v8a-release.apk",
            "BakaSU_Pro_v4.2.0-rc3_0-arm64-v8a-release.apk",
            "BakaSU_Pro__35244-arm64-v8a-release.apk",
            "BakaSU_Pro_v4.2.0-rc3_35244-arm64-v8a-release.apk.zip",
        )) {
            assertNull(fileName, ManagerUpdateSource.parseApkName(fileName))
        }
    }
}
