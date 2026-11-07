package com.pab.aitmp.aiis.godp.planning.services.tasks;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.PlanningJobRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.res.PlanningJobResult;
import com.pab.aitmp.aiis.godp.planning.services.tasks.PlanningTaskService.Kind;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

class PlanningJobHandlersTest {
  private final Instant now=Instant.parse("2026-11-07T08:00:00Z");
  @Test void failedPageRetainsCursorWhileIndependentContentStagesContinue() {
    PlanningTaskService tasks=mock(PlanningTaskService.class);
    when(tasks.run(any(),eq(now),anyInt(),anyLong())).thenReturn(map("status","processed"));
    when(tasks.run(Kind.MARKETING_STATUS,now,500,42)).thenReturn(map("status","retry_required","next_after_id",90L,"has_more",true));
    PlanningJobResult result=new ContentCompletionHandler(tasks).run(new PlanningJobRequest(now,500,Collections.singletonMap("MARKETING_STATUS",42L),false));
    assertEquals("retry_required",result.status);
    assertEquals(42L,result.nextCursors.get("MARKETING_STATUS"));
    assertTrue(result.needsNextTick); assertFalse(result.businessComplete);
    verify(tasks).run(Kind.MARKETING_STATUS,now,500,42);
    verify(tasks).run(Kind.CONTENT_STATUS,now,200,0);
    verify(tasks,never()).run(eq(Kind.CONTENT_FLOW),any(),anyInt(),anyLong());
  }
  @Test void contentDispatchRequiresItsExplicitThreeTimesDailyTriggerAndStatusLimitIsBounded() {
    PlanningTaskService tasks=mock(PlanningTaskService.class);
    when(tasks.run(any(),eq(now),anyInt(),anyLong())).thenReturn(map("status","processed","has_more",false));
    ContentCompletionHandler handler=new ContentCompletionHandler(tasks);
    handler.run(new PlanningJobRequest(now,500,Collections.emptyMap(),false));
    verify(tasks).run(Kind.CONTENT_STATUS,now,200,0);
    verify(tasks,never()).run(eq(Kind.CONTENT_FLOW),any(),anyInt(),anyLong());
    handler.run(new PlanningJobRequest(now,500,Collections.emptyMap(),true));
    verify(tasks).run(Kind.CONTENT_FLOW,now,500,0);
  }
  @Test void acceptedAlgorithmWorkIsNeverBusinessCompletion() {
    PlanningTaskService tasks=mock(PlanningTaskService.class);
    when(tasks.run(any(),eq(now),anyInt(),anyLong())).thenReturn(map("status","processed"));
    when(tasks.run(Kind.ALGORITHM,now,100,0)).thenReturn(map("status","accepted"));
    PlanningJobResult result=new AutoScheduleHandler(tasks).run(new PlanningJobRequest(now,100,Collections.emptyMap(),false));
    assertFalse(result.businessComplete); assertTrue(result.needsNextTick);
  }
}
