package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningJobHandler;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PlanningJobRequest;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.res.PlanningJobResult;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService.Kind;
import java.util.*;
import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;

/** Host-neutral phase composition; errors propagate and failed pages retain their old cursor. */
abstract class CompositePlanningJobHandler implements PlanningJobHandler {
  private final PlanningTaskService tasks;
  private final List<Kind> kinds;
  CompositePlanningJobHandler(PlanningTaskService tasks, Kind... kinds) {
    this.tasks=Objects.requireNonNull(tasks); this.kinds=Arrays.asList(kinds);
  }
  protected boolean independentStages() { return false; }
  public final PlanningJobResult run(PlanningJobRequest request) {
    for (String cursor:request.cursors.keySet()) Kind.valueOf(cursor);
    PlanningJobResult result=new PlanningJobResult();
    result.handler=getClass().getSimpleName(); result.status="processed";
    result.nextCursors.putAll(request.cursors);
    for(Kind kind:kinds) {
      if(kind==Kind.CONTENT_FLOW && !request.dispatchContentFlow) continue;
      long previous=request.cursors.getOrDefault(kind.name(),0L);
      int limit=kind==Kind.CONTENT_STATUS ? Math.min(200, request.batchSize) : request.batchSize;
      Map<String,Object> phase;
      try {
        phase=tasks.run(kind,request.now,limit,previous);
      } catch(RuntimeException failure) {
        if(!independentStages()) throw failure;
        phase=map("status","retry_required","has_more",false,"needs_next_tick",true,
            "error_type",failure.getClass().getSimpleName());
      }
      Map<String,Object> reported=new LinkedHashMap<>(phase);
      reported.put("phase",kind.name()); result.phases.add(reported);
      boolean retry="retry_required".equals(text(phase,"status"));
      boolean more=Boolean.TRUE.equals(phase.get("has_more"));
      result.needsNextTick |= retry || more || Boolean.TRUE.equals(phase.get("needs_next_tick"))
          || "accepted".equals(phase.get("status"));
      if(retry) {
        result.status="retry_required";
        if(independentStages()) continue;
        return result;
      }
      result.nextCursors.put(kind.name(), more ? number(phase,"next_after_id") : 0L);
    }
    return result;
  }
}
