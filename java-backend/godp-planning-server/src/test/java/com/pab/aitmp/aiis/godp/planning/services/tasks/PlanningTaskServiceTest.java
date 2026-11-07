package com.pab.aitmp.aiis.godp.planning.services.tasks;

import com.pab.aitmp.aiis.godp.planning.services.content.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentFlowDispatchService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualContentStatusService;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.planning.client.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.planning.services.auto.AutoScheduleService;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

class PlanningTaskServiceTest {
  @Test
  void paginationFailuresAndAcceptanceRemainVisibleToHost() {
    ManualContentStatusService content = mock(ManualContentStatusService.class);
    AutoScheduleService auto = mock(AutoScheduleService.class);
    PythonExecutionClient python = mock(PythonExecutionClient.class);
    PlanningTaskService tasks =
        new PlanningTaskService(null, null, auto, null, null, content, null, python);
    Instant now = Instant.parse("2026-11-03T08:00:00Z");
    when(content.reconcile(20, 42)).thenReturn(map("has_more", true, "next_after_id", 65L));
    assertEquals(
        65L, tasks.run(PlanningTaskService.Kind.CONTENT_STATUS, now, 20, 42).get("next_after_id"));
    verify(content, times(1)).reconcile(20, 42);
    when(content.reconcile(20, 65)).thenThrow(new BusinessException(503, "内容来源不可用"));
    assertThrows(
        BusinessException.class,
        () -> tasks.run(PlanningTaskService.Kind.CONTENT_STATUS, now, 20, 65));
    Map<String, Object> signal = tasks.run(PlanningTaskService.Kind.ALGORITHM, now, 20, 0);
    assertEquals("accepted", signal.get("status"));
    assertEquals(false, signal.get("business_complete"));
    verify(python).wakeup(Arrays.asList("planning", "manual_compute"));
    when(auto.advanceOpen(now,20))
        .thenReturn(Collections.singletonList(map("status", "retry_pending")));
    when(auto.tick(now)).thenReturn(map("status", "not_due"));
    assertEquals(
        "retry_required", tasks.run(PlanningTaskService.Kind.AUTOMATIC, now, 20, 0).get("status"));
    assertThrows(
        IllegalArgumentException.class,
        () -> tasks.run(PlanningTaskService.Kind.HOTSPOT, now, 0, 0));
    assertEquals(503, assertThrows(BusinessException.class,
        () -> tasks.run(PlanningTaskService.Kind.CONTENT_FLOW, now, 100, 0)).status);
  }

  @Test
  void hostCanRunContentFlowWithoutIntroducingAnInternalTimer() {
    ContentFlowDispatchService flow = mock(ContentFlowDispatchService.class);
    Instant now = Instant.parse("2026-11-05T08:00:00Z");
    when(flow.scan(now, 100, 42)).thenReturn(map("status", "processed", "has_more", false));
    PlanningTaskService tasks = new PlanningTaskService(null, null, null, null, null, null, null, null, flow);
    assertEquals("processed", tasks.run(PlanningTaskService.Kind.CONTENT_FLOW, now, 100, 42).get("status"));
    verify(flow).scan(now, 100, 42);
  }

  @Test
  void stagedAutomaticWritesAskHostForAnotherTickWithoutReportingFailure() {
    AutoScheduleService auto = mock(AutoScheduleService.class);
    Instant now = Instant.parse("2026-11-07T08:00:00Z");
    when(auto.advanceOpen(now,100)).thenReturn(Collections.emptyList());
    when(auto.tick(now)).thenReturn(map("status", "persisting", "task", map("status", "计算中")));
    PlanningTaskService tasks = new PlanningTaskService(null, null, auto, null, null, null, null, null);
    Map<String, Object> report = tasks.run(PlanningTaskService.Kind.AUTOMATIC, now, 100, 0);
    assertEquals("processed", report.get("status"));
    assertEquals(true, report.get("needs_next_tick"));
    when(auto.tick(now)).thenReturn(map("status", "completed", "task", map("status", "已完成")));
    assertEquals(false, tasks.run(PlanningTaskService.Kind.AUTOMATIC, now, 100, 0).get("needs_next_tick"));
  }
}
