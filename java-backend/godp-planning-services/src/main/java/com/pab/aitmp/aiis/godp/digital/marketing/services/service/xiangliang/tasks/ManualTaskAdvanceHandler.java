package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService.Kind.*;
public final class ManualTaskAdvanceHandler extends CompositePlanningJobHandler {
  public ManualTaskAdvanceHandler(PlanningTaskService tasks) { super(tasks,CONFIGURATION,MANUAL,ALGORITHM); }
}
