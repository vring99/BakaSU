package org.bakasu.bakasu.data.update

import java.net.URLEncoder
import java.nio.charset.StandardCharsets

internal object ManagerUpdateSource {
    private const val REPOSITORY = "vring99/BakaSU"
    private const val WORKFLOW_FILE = "build-private-manager.yml"
    private const val BRANCH = "codex/build-35233"
    private const val RELEASE_ARTIFACT = "BakaSU-Pro-release"
    private const val API_URL = "https://api.github.com/repos/$REPOSITORY"

    val stableUrl = "$API_URL/releases/latest"
    val betaRunsUrl = "$API_URL/actions/workflows/$WORKFLOW_FILE/runs" +
        "?branch=${URLEncoder.encode(BRANCH, StandardCharsets.UTF_8.name())}" +
        "&status=success&per_page=1"

    private val managerApkPattern = Regex(
        "^BakaSU_Pro_(.+)_(\\d+)-(arm64-v8a|armeabi-v7a|x86_64|riscv64|universal)-release\\.apk$",
    )

    fun artifactUrl(runId: Long): String = "https://nightly.link/$REPOSITORY/actions/runs/$runId/$RELEASE_ARTIFACT.zip"

    fun commitsUrl(commitSha: String): String = "$API_URL/commits?sha=$commitSha&per_page=1"

    fun parseApkName(fileName: String): ManagerApkName? {
        val match = managerApkPattern.matchEntire(fileName) ?: return null
        val versionCode = match.groupValues[2].toIntOrNull()?.takeIf { it > 0 } ?: return null
        return ManagerApkName(
            versionName = match.groupValues[1],
            versionCode = versionCode,
            abi = match.groupValues[3],
            fileName = fileName,
        )
    }
}

internal data class ManagerApkName(
    val versionName: String,
    val versionCode: Int,
    val abi: String,
    val fileName: String,
)
