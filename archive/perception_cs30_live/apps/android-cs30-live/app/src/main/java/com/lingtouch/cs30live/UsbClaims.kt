package com.lingtouch.cs30live

/** Shared policy, with callbacks so rollback and alternate-interface cases are testable. */
object UsbClaims {
    fun forceAll(interfaceIds: List<Int>, claim: (Int) -> Boolean, release: (Int) -> Boolean,
                 describe: (Int) -> String, log: (String) -> Unit): List<Int> {
        val ids = interfaceIds.distinct().sorted()
        require(0 in ids && 1 in ids) { "CS30 缺少接口 0 或 1：$ids" }
        require(ids.all { it in 0..255 }) { "USB 接口号无效：$ids" }
        val claimed = mutableListOf<Int>()
        try {
            for (id in ids) {
                val before = describe(id)
                log("Java before force claim: $before")
                check(claim(id)) { "Java force claim 接口 $id 失败；$before" }
                claimed.add(id)
                log("Java force claim OK: ${describe(id)}")
            }
            return claimed.toList()
        } catch (error: Throwable) {
            claimed.asReversed().forEach { id ->
                val result = runCatching { release(id) }
                log("Java rollback release interface=$id: ${result.getOrNull() ?: result.exceptionOrNull()?.message}")
            }
            throw error
        }
    }
}
