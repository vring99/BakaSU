package org.bakasu.bakasu.data.shell

import org.junit.Assert.assertEquals
import org.junit.Test

class ShellQuoteTest {
    @Test
    fun preservesSpecialCharactersAsLiteralArguments() {
        assertEquals("''", shellQuote(""))
        assertEquals("'a'\"'\"'b'", shellQuote("a'b"))
        assertEquals("'\$(text); `text` \"value\"\nnext'", shellQuote("\$(text); `text` \"value\"\nnext"))
    }
}
