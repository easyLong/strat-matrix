package com.pab.aitmp.aiis.godp.planning.services.tasks;
import static com.pab.aitmp.aiis.godp.planning.services.tasks.PlanningTaskService.Kind.*;
public final class ManualTaskAdvanceHandler extends CompositePlanningJobHandler {
  public ManualTaskAdvanceHandler(PlanningTaskService tasks) { super(tasks,CONFIGURATION,MANUAL,ALGORITHM); }
}
