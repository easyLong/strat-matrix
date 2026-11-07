package com.pab.aitmp.aiis.godp.planning.entity.vo.req;

import java.time.Instant;
import java.util.*;

/** One host-triggered bounded pass. Content-flow dispatch is opted in on its three daily triggers. */
public final class PlanningJobRequest {
  public final Instant now;
  public final int batchSize;
  public final Map<String,Long> cursors;
  public final boolean dispatchContentFlow;
  public PlanningJobRequest(Instant now, int size, Map<String,Long> cursors, boolean dispatch) {
    if(now==null || size<1 || size>500 || cursors==null
        || cursors.values().stream().anyMatch(v -> v==null || v<0))
      throw new IllegalArgumentException("调度时间、批量或游标无效");
    this.now=now; this.batchSize=size;
    this.cursors=Collections.unmodifiableMap(new LinkedHashMap<>(cursors));
    this.dispatchContentFlow=dispatch;
  }
}
