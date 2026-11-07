package com.pab.aitmp.aiis.godp.planning.server.dev;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.time.*;
import java.util.Map;
import java.util.function.BiFunction;

/**
 * Outside only: simulate one daily host job, retaining pagination and retry on the existing pulse.
 */
public final class LocalDailyHotspotCheck {
  private final BiFunction<Instant, Long, Map<String, Object>> scan;
  private LocalDate scanDay, completedDay;
  private long after;

  public LocalDailyHotspotCheck(BiFunction<Instant, Long, Map<String, Object>> scan) {
    this.scan = scan;
  }

  public synchronized Map<String, Object> run(Instant now) {
    LocalDate today = now.atZone(ZoneId.of("Asia/Shanghai")).toLocalDate();
    if (today.equals(completedDay)) return map("status", "already_checked", "applied", 0);
    if (!today.equals(scanDay)) {
      scanDay = today;
      after = 0;
    }
    Map<String, Object> result = scan.apply(now, after);
    if (Boolean.TRUE.equals(result.get("has_more"))) after = number(result, "next_after_id");
    else {
      completedDay = today;
      after = 0;
    }
    return result;
  }
}
