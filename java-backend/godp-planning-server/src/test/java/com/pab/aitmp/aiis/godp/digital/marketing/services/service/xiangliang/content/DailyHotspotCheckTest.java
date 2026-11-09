package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualContentStatusService;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.ReadDatabaseFixture;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalDailyHotspotCheck;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class DailyHotspotCheckTest {
  @Test
  void queriesOnlyTomorrowAndDoesNotReadTopicsWhenNoEmptySlotsRemain() throws Exception {
    ReadDatabaseFixture db = new ReadDatabaseFixture();
    db.batch(1, "auto", "2030-01-07");
    for (String date : Arrays.asList("2030-01-07", "2030-01-08", "2030-01-09", "2030-01-10"))
      db.item(1, "A", date, "unassigned", "hotspot", "");
    PlanningContentPort source = mock(PlanningContentPort.class);
    Instant morning = Instant.parse("2030-01-08T01:00:00Z"); // Beijing 09:00, no 22:00 restriction.
    when(source.hotspots(morning)).thenReturn(Collections.emptyList());
    SlotCompletionService service =
        new SlotCompletionService(
            db.slots,
            db.repo,
            source,
            new ManualContentStatusService(db.repo, c -> Collections.emptyList()));
    assertEquals(1, number(service.hotspots(morning, 100, 0), "applied"));
    for (Map<String, Object> row : db.repo.itemsByBatch(1))
      assertEquals(
          text(row, "publish_date").equals("2030-01-09") ? "planned" : "unassigned",
          row.get("production_status"));
    assertEquals(0, number(service.hotspots(morning, 100, 0), "applied"));
    assertEquals(
        0, number(service.hotspots(Instant.parse("2030-01-10T01:00:00Z"), 100, 0), "applied"));
    verify(source, times(1)).hotspots(any());
  }

  @Test
  void localSimulationFinishesAllPagesOncePerBeijingDay() {
    List<Long> seen = new ArrayList<>();
    LocalDailyHotspotCheck daily =
        new LocalDailyHotspotCheck(
            (now, after) -> {
              seen.add(after);
              return after == 0
                  ? map("has_more", true, "next_after_id", 10)
                  : map("has_more", false, "applied", 1);
            });
    Instant now = Instant.parse("2030-01-08T15:59:00Z");
    daily.run(now);
    daily.run(now.plusSeconds(1));
    daily.run(now.plusSeconds(2));
    assertEquals(Arrays.asList(0L, 10L), seen);
    daily.run(Instant.parse("2030-01-08T16:00:00Z"));
    assertEquals(Arrays.asList(0L, 10L, 0L), seen);
    assertEquals(
        LocalDate.of(2030, 1, 10),
        SlotCompletionService.hotspotPublishDate(Instant.parse("2030-01-08T16:00:00Z")));
  }

  @Test
  void failedDailyCheckCanRetryAndEmptyCheckStopsForTheDay() {
    AtomicInteger calls = new AtomicInteger();
    LocalDailyHotspotCheck daily =
        new LocalDailyHotspotCheck(
            (now, after) -> {
              if (calls.getAndIncrement() == 0)
                throw new IllegalStateException("temporary source failure");
              return map("has_more", false, "applied", 0);
            });
    Instant now = Instant.parse("2030-01-08T01:00:00Z");
    assertThrows(IllegalStateException.class, () -> daily.run(now));
    daily.run(now.plusSeconds(1));
    daily.run(now.plusSeconds(2));
    assertEquals(2, calls.get());
  }
}
