package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.context.PlanningRequestContext;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import java.util.*;

/**
 * Request-thread scope only. Never inherited by executors; background jobs use persisted actors.
 */
public final class RequestContexts {
  public static final String TRACE_HEADER = "X-Request-Id";
  private static final ThreadLocal<PlanningRequestContext> CURRENT = new ThreadLocal<>();

  private RequestContexts() {}

  public static Optional<PlanningRequestContext> current() {
    return Optional.ofNullable(CURRENT.get());
  }

  public static PlanningRequestContext require() {
    return current().orElseThrow(() -> new BusinessException(401, "可信请求上下文尚未建立"));
  }

  public static Scope open(PlanningRequestContext value) {
    return new Scope(Objects.requireNonNull(value));
  }

  public static ManualPorts.Actor actor(ManualPorts.Actor fallback) {
    Objects.requireNonNull(fallback);
    return () -> current().map(value -> value.userUm).orElseGet(fallback::current);
  }

  public static final class Scope implements AutoCloseable {
    private final PlanningRequestContext previous;
    private final Thread owner = Thread.currentThread();
    private boolean closed;

    private Scope(PlanningRequestContext value) {
      previous = CURRENT.get();
      CURRENT.set(value);
    }

    public void close() {
      if (Thread.currentThread() != owner) throw new IllegalStateException("请求上下文必须在原线程关闭");
      if (!closed) {
        if (previous == null) CURRENT.remove();
        else CURRENT.set(previous);
        closed = true;
      }
    }
  }
}
