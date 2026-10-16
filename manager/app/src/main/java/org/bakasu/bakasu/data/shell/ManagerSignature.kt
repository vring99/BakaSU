package org.bakasu.bakasu.data.shell

import org.bakasu.bakasu.BuildConfig

internal fun isExpectedManagerSignature(commandSucceeded: Boolean, output: List<String>): Boolean = commandSucceeded &&
    output.singleOrNull()?.trim() == BuildConfig.EXPECTED_MANAGER_SIGNATURE
