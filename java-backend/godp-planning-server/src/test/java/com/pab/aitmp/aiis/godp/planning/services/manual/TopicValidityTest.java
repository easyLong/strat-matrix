package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.map;
import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import java.util.Map;
import org.junit.jupiter.api.Test;

class TopicValidityTest {
  @Test
  void comparesInclusiveBeijingDatesRatherThanUtcPrefixesOrCurrentTime() {
    Map<String, Object> topic = map("valid_from", "2026-11-05T16:00:00Z",
        "valid_to", "2026-11-07T15:59:59Z");
    assertFalse(TopicValidity.includes(topic, LocalDate.parse("2026-11-05")));
    assertTrue(TopicValidity.includes(topic, LocalDate.parse("2026-11-06")));
    assertTrue(TopicValidity.includes(topic, LocalDate.parse("2026-11-07")));
    assertFalse(TopicValidity.includes(topic, LocalDate.parse("2026-11-08")));
    assertTrue(TopicValidity.includes(map(), LocalDate.parse("2027-01-01")));
    assertEquals(502, assertThrows(BusinessException.class,
        () -> TopicValidity.includes(map("valid_from", "invalid"), LocalDate.now())).status);
  }
}
