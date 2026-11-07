package com.pab.aitmp.aiis.godp.planning.api.port;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.PlanningJobRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.res.PlanningJobResult;

/** No scheduler SDK dependency. The bank's job invokes one handler and persists returned cursors. */
public interface PlanningJobHandler {
  PlanningJobResult run(PlanningJobRequest request);
}
