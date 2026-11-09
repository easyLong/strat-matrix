package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port;
import java.util.function.Supplier;

/** Small database unit of work; callers keep remote I/O outside this boundary. */
public interface BusinessTransactions { <T> T required(Supplier<T> work); }
