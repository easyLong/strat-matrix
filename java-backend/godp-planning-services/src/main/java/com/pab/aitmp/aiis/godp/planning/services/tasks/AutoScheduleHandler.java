package com.pab.aitmp.aiis.godp.planning.services.tasks;
import static com.pab.aitmp.aiis.godp.planning.services.tasks.PlanningTaskService.Kind.*;
public final class AutoScheduleHandler extends CompositePlanningJobHandler {
  public AutoScheduleHandler(PlanningTaskService tasks) { super(tasks,CONFIGURATION,AUTOMATIC,ALGORITHM); }
}
