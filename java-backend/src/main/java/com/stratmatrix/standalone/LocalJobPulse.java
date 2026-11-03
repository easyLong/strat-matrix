package com.stratmatrix.standalone;

import com.stratmatrix.planning.adapter.python.PythonExecutionClient;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;

/** Java本地调度脉冲；任务状态与恢复依据始终在持久化业务队列中。 */
public class LocalJobPulse {
  private static final Logger LOG = LoggerFactory.getLogger(LocalJobPulse.class);
  private final PythonExecutionClient client;
  private final LongSupplier clock;
  private final Map<String, Long> intervals = new LinkedHashMap<>();
  private final Map<String, Long> nextDue = new LinkedHashMap<>();
  private String lastFailure = "";
  private Runnable advanceManual = () -> {};
  private Runnable advanceAuto;
  private long nextAutoDue = Long.MIN_VALUE;

  public LocalJobPulse(PythonExecutionClient client) {
    this(client, () -> TimeUnit.NANOSECONDS.toMillis(System.nanoTime()));
  }

  public LocalJobPulse(PythonExecutionClient client, Runnable advanceManual) {
    this(client);
    this.advanceManual = advanceManual;
  }

  public LocalJobPulse(PythonExecutionClient client, LongSupplier clock) {
    this.client = client;
    this.clock = clock;
    intervals.put("manual", 2000L);
    intervals.put("planning", 10000L);
    intervals.put("weekly", 60000L);
    intervals.put("hotspot", 60000L);
  }

  /** The Java business task owns the weekly trigger after the host enables it. */
  public void enableJavaWeekly(Runnable tick) {
    advanceAuto = tick;
    intervals.remove("weekly");
  }

  public void enableJavaBusinessOwnership() {
    intervals.remove("manual");
    intervals.remove("hotspot");
    intervals.put("manual_compute", 2000L);
  }

  @Scheduled(fixedDelay = 1000, initialDelay = 1000)
  public void pulse() {
    try {
      advanceManual.run();
    } catch (RuntimeException failure) {
      LOG.warn("Java人工策划推进暂不可用，将在下一次调度重试");
    }
    long now = clock.getAsLong();
    if (advanceAuto != null && now >= nextAutoDue) {
      nextAutoDue = now + 60000L;
      try {
        advanceAuto.run();
      } catch (RuntimeException failure) {
        LOG.warn("Java自动策划触发暂不可用，将在下一次调度重试：{}", failure.getClass().getSimpleName());
      }
    }
    List<String> due = new ArrayList<>();
    intervals.forEach(
        (job, interval) -> {
          if (now >= nextDue.getOrDefault(job, Long.MIN_VALUE)) due.add(job);
        });
    if (due.isEmpty()) return;
    try {
      client.wakeup(due);
      // Only receipt advances the timer. Network/auth errors are retried next tick.
      due.forEach(job -> nextDue.put(job, now + intervals.get(job)));
      if (!lastFailure.isEmpty()) LOG.info("Python后台执行触发已恢复");
      lastFailure = "";
    } catch (RuntimeException failure) {
      String category = failure.getClass().getSimpleName();
      if (!category.equals(lastFailure)) LOG.warn("Python后台执行触发未就绪：{}，将重试；请核对内部令牌及连接", category);
      lastFailure = category;
    }
  }
}
