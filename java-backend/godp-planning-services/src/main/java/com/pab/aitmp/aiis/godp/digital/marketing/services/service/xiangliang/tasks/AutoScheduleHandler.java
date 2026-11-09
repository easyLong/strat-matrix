package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService.Kind.*;
public final class AutoScheduleHandler extends CompositePlanningJobHandler {
  public AutoScheduleHandler(PlanningTaskService tasks) { super(tasks,CONFIGURATION,AUTOMATIC,ALGORITHM); }
}
