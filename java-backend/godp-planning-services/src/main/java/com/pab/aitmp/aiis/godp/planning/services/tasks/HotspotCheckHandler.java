package com.pab.aitmp.aiis.godp.planning.services.tasks;
import static com.pab.aitmp.aiis.godp.planning.services.tasks.PlanningTaskService.Kind.*;
public final class HotspotCheckHandler extends CompositePlanningJobHandler {
  public HotspotCheckHandler(PlanningTaskService tasks) { super(tasks,HOTSPOT); }
}
