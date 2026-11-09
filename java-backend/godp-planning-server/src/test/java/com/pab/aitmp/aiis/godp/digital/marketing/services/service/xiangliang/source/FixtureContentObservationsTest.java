package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local.FixtureContentObservations;
import java.util.*;
import org.junit.jupiter.api.Test;

class FixtureContentObservationsTest {
  @Test
  void noFactsDoNotManufactureCompletion() {
    SourceFacts source = mock(SourceFacts.class);
    when(source.productionStatus(anyMap())).thenReturn(Collections.emptyList());
    assertTrue(
        new FixtureContentObservations(source)
            .content(Collections.singletonList(new ManualPorts.ContentCandidate(1, "S1", 1, "T1")))
            .isEmpty());
  }

  @Test
  void onlyExplicitCurrentVersionCanBeProjectedAndAmbiguousSlotsFail() {
    SourceFacts source = mock(SourceFacts.class);
    when(source.productionStatus(anyMap()))
        .thenReturn(
            Collections.singletonList(
                map(
                    "slot_id",
                    "S1",
                    "version",
                    2,
                    "status",
                    "已完成",
                    "content_id",
                    "C1",
                    "updated_at",
                    "2026-11-03T08:00:00Z")));
    FixtureContentObservations adapter = new FixtureContentObservations(source);
    assertTrue(
        adapter
            .content(Collections.singletonList(new ManualPorts.ContentCandidate(1, "S1", 1, "T1")))
            .isEmpty());
    ManualPorts.ContentCandidate current = new ManualPorts.ContentCandidate(1, "S1", 2, "T1");
    assertEquals("C1", adapter.content(Collections.singletonList(current)).get(0).contentId);
    assertThrows(
        BusinessException.class,
        () ->
            adapter.content(
                Arrays.asList(current, new ManualPorts.ContentCandidate(2, "S1", 2, "T2"))));
  }
}
