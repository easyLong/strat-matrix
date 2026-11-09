package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev;

import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;

/** Outside only: one timer invokes the same four SDK-free handlers used by the host. */
public final class LocalJobPulse {
  private static final Logger LOG=LoggerFactory.getLogger(LocalJobPulse.class);
  private final Map<String,Runnable> handlers;
  private final Map<String,Long> due=new LinkedHashMap<>();
  private final Map<String,Long> intervals=new LinkedHashMap<>();
  private final LongSupplier clock;
  public LocalJobPulse(Map<String,Runnable> handlers) {
    this(handlers,() -> TimeUnit.NANOSECONDS.toMillis(System.nanoTime()));
  }
  public LocalJobPulse(Map<String,Runnable> handlers, LongSupplier clock) {
    intervals.put("manual",2000L); intervals.put("automatic",60000L);
    intervals.put("content",30000L); intervals.put("hotspot",60000L);
    if(!handlers.keySet().equals(intervals.keySet())) throw new IllegalArgumentException("Four planning handlers required");
    this.handlers=new LinkedHashMap<>(handlers); this.clock=Objects.requireNonNull(clock);
  }
  @Scheduled(fixedDelay=1000,initialDelay=1000)
  public synchronized void pulse() {
    long now=clock.getAsLong();
    handlers.forEach((name,handler) -> {
      if(now<due.getOrDefault(name,Long.MIN_VALUE)) return;
      try {
        handler.run(); due.put(name,now+intervals.get(name));
      } catch(RuntimeException failure) {
        LOG.warn("Planning development pass needs retry: handler={}, category={}",name,failure.getClass().getSimpleName());
      }
    });
  }
}
