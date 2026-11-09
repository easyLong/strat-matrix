package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PlanningJobRequest;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.res.PlanningJobResult;

/** No scheduler SDK dependency. The bank's job invokes one handler and persists returned cursors. */
public interface PlanningJobHandler {
  PlanningJobResult run(PlanningJobRequest request);
}
