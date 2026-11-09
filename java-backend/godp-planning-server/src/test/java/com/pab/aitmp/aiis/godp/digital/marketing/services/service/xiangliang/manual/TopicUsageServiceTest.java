package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class TopicUsageServiceTest {
  @Test
  void preservesRequestedOrderAndFillsZeroFromCompletedBusinessCounts() {
    ManualRepository repository = mock(ManualRepository.class);
    when(repository.completedTopicUsage(Arrays.asList("B", "A")))
        .thenReturn(Collections.singletonList(map("topic_id", "A", "official_use_count", 2L)));
    Map<String, Object> result =
        new TopicUsageService(repository).query(map("topic_ids", Arrays.asList("B", "A")));
    List<Map<String, Object>> counts = rows(result.get("topic_results"));
    assertEquals("success", result.get("status"));
    assertNotNull(result.get("queried_at"));
    assertEquals("B", text(counts.get(0), "topic_id"));
    assertEquals(0, number(counts.get(0), "official_use_count"));
    assertEquals(2, number(counts.get(1), "official_use_count"));
  }

  @Test
  void rejectsInvalidIdsBeforeSqlAndSupportsChineseContractAlias() {
    ManualRepository repository = mock(ManualRepository.class);
    TopicUsageService service = new TopicUsageService(repository);
    for (Object input :
        Arrays.asList(
            Collections.emptyList(),
            Arrays.asList("A", "A"),
            Arrays.asList(" A"),
            Arrays.asList(1)))
      assertThrows(BusinessException.class, () -> service.query(map("topic_ids", input)));
    assertThrows(
        BusinessException.class,
        () ->
            service.query(
                map("topic_ids", Collections.singletonList("A"), "started_at", "2026-11-03")));
    verifyNoInteractions(repository);
    when(repository.completedTopicUsage(Collections.singletonList("A")))
        .thenReturn(Collections.emptyList());
    assertEquals(
        1,
        rows(service.query(map("选题ID列表", Collections.singletonList("A"))).get("topic_results"))
            .size());
  }
}
