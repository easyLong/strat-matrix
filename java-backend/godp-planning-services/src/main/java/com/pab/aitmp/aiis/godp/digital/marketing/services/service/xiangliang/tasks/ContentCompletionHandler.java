package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskService.Kind.*;
public final class ContentCompletionHandler extends CompositePlanningJobHandler {
  public ContentCompletionHandler(PlanningTaskService tasks) {
    super(tasks,MARKETING_STATUS,MARKETING_PLACEMENT,MARKETING,CONTENT_STATUS,CONTENT_FLOW);
  }
  @Override protected boolean independentStages() { return true; }
}
