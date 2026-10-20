package org.bakasu.bakasu.ui.screen.main

import org.bakasu.bakasu.R
import org.bakasu.bakasu.domain.model.InstalledModule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ModulePreinitTest {
    private val module = InstalledModule(
        id = "test",
        name = "test",
        author = "test",
        version = "1",
        versionCode = 1,
        description = "",
        enabled = true,
        update = false,
        remove = false,
        updateJson = "",
        hasWebUi = false,
        hasActionScript = false,
        metamodule = false,
        actionIconPath = null,
        webUiIconPath = null,
        dirId = "test",
        moduleUpdate = null,
    )

    @Test
    fun mapsEachPreinitFailureToItsWarning() {
        val warnings = mapOf(
            "no_space" to R.string.module_preinit_no_space,
            "error" to R.string.module_preinit_error,
            "bootloop" to R.string.module_preinit_bootloop,
            "unsupported" to R.string.module_preinit_unsupported,
        )

        warnings.forEach { (status, warning) ->
            assertEquals(status, warning, module.copy(preinitStatus = status).preinitWarning())
        }
    }

    @Test
    fun hidesWarningForSuccessfulAbsentAndUnknownStatuses() {
        listOf("", "ok", "future_status").forEach { status ->
            assertNull(status, module.copy(preinitStatus = status).preinitWarning())
        }
    }

    @Test
    fun defaultsToNoWarningForOlderDaemons() {
        assertEquals("", module.preinitStatus)
        assertNull(module.preinitWarning())
    }
}
