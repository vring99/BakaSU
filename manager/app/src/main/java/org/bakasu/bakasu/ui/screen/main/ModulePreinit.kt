package org.bakasu.bakasu.ui.screen.main

import androidx.annotation.StringRes
import org.bakasu.bakasu.R
import org.bakasu.bakasu.domain.model.InstalledModule

/** Warning when a module's preinit actions will not run on the next boot. */
@StringRes
internal fun InstalledModule.preinitWarning(): Int? = when (preinitStatus) {
    "no_space" -> R.string.module_preinit_no_space
    "error" -> R.string.module_preinit_error
    "bootloop" -> R.string.module_preinit_bootloop
    "unsupported" -> R.string.module_preinit_unsupported
    else -> null
}
