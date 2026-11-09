package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourcePageReader.Capability.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.*;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class SourcePageReaderTest {
  private Map<String, Object> page(Map<String, Object> q, List<Map<String, Object>> rows) {
    int number = ((Number) q.get("page_no")).intValue(),
        size = ((Number) q.get("page_size")).intValue();
    int offset = Math.min(rows.size(), (number - 1) * size);
    return map(
        "items",
        rows.subList(offset, Math.min(rows.size(), offset + size)),
        "total",
        rows.size(),
        "page_no",
        number,
        "page_size",
        size);
  }

  @Test
  void firstAndAllHaveExplicitLimitsAndDoNotModifyFilters() {
    SourceFacts facts = mock(SourceFacts.class);
    List<Map<String, Object>> input =
        Arrays.asList(map("topic_id", "T1"), map("topic_id", "T2"), map("topic_id", "T3"));
    AtomicInteger calls = new AtomicInteger();
    when(facts.topics(anyMap()))
        .thenAnswer(
            call -> {
              calls.incrementAndGet();
              return page(call.getArgument(0), input);
            });
    SourcePageReader reader = new SourcePageReader(facts, 2, 3);
    Map<String, Object> filter = map("source", "热点");
    String original = write(filter);
    assertEquals(1, reader.first(TOPICS, filter, 1).size());
    assertEquals(1, calls.get());
    assertEquals(3, reader.all(TOPICS, filter).size());
    assertEquals(3, calls.get());
    assertEquals(original, write(filter));
    reader.first(TOPICS, filter, 0);
    assertEquals(3, calls.get());
    assertThrows(IllegalArgumentException.class, () -> reader.first(TOPICS, filter, 7));
  }

  @Test
  void idRequestsAreDeduplicatedSplitAtFiveHundredAndScoped() {
    SourceFacts facts = mock(SourceFacts.class);
    AtomicInteger calls = new AtomicInteger();
    when(facts.accounts(anyMap()))
        .thenAnswer(
            call -> {
              Map<String, Object> q = call.getArgument(0);
              List<?> ids = (List<?>) q.get("account_ids");
              assertTrue(ids.size() <= 500);
              calls.incrementAndGet();
              List<Map<String, Object>> records = new ArrayList<>();
              for (Object id : ids) records.add(map("account_id", id));
              return page(q, records);
            });
    List<String> ids = new ArrayList<>();
    for (int i = 0; i < 501; i++) ids.add("A" + i);
    ids.add("A0");
    SourcePageReader reader = new SourcePageReader(facts);
    assertEquals(501, reader.byIds(ACCOUNTS, ids, 1000).size());
    assertEquals(2, calls.get());
    assertEquals(502, ids.size());
    reader.byIds(ACCOUNTS, Collections.emptyList(), 100);
    assertEquals(2, calls.get());
    doReturn(
            map(
                "items",
                Collections.singletonList(map("account_id", "OUTSIDE")),
                "total",
                1,
                "page_no",
                1,
                "page_size",
                500))
        .when(facts)
        .accounts(anyMap());
    assertThrows(
        BusinessException.class, () -> reader.byIds(ACCOUNTS, Collections.singletonList("A1"), 10));
  }

  @Test
  void duplicatePagesChangingTotalsAndIncompleteResultsNeverReturnPartialSuccess() {
    SourceFacts facts = mock(SourceFacts.class);
    SourcePageReader reader = new SourcePageReader(facts, 1, 3);
    when(facts.topics(anyMap()))
        .thenAnswer(
            call -> {
              Map<String, Object> q = call.getArgument(0);
              return map(
                  "items",
                  Collections.singletonList(map("topic_id", "T1")),
                  "total",
                  2,
                  "page_no",
                  q.get("page_no"),
                  "page_size",
                  1);
            });
    assertEquals(
        502, assertThrows(BusinessException.class, () -> reader.all(TOPICS, map())).status);
    doAnswer(
            call -> {
              Map<String, Object> q = call.getArgument(0);
              int p = ((Number) q.get("page_no")).intValue();
              return map(
                  "items",
                  Collections.singletonList(map("topic_id", "T" + p)),
                  "total",
                  p == 1 ? 2 : 3,
                  "page_no",
                  p,
                  "page_size",
                  1);
            })
        .when(facts)
        .topics(anyMap());
    assertEquals(
        409, assertThrows(BusinessException.class, () -> reader.all(TOPICS, map())).status);
    for (Map<String, Object> malformed :
        Arrays.asList(
            map("items", Collections.emptyList(), "total", 2, "page_no", 1, "page_size", 1),
            map("items", "wrong", "total", 1, "page_no", 1, "page_size", 1),
            map(
                "items",
                Collections.singletonList(map("topic_id", "T1")),
                "total",
                1.5,
                "page_no",
                1,
                "page_size",
                1),
            map(
                "items",
                Collections.singletonList(map("topic_id", "T1")),
                "total",
                1,
                "page_no",
                2,
                "page_size",
                1))) {
      doReturn(malformed).when(facts).topics(anyMap());
      assertEquals(
          502, assertThrows(BusinessException.class, () -> reader.all(TOPICS, map())).status);
    }
  }

  @Test
  void completeReadsRejectOversizedSetsAndByIdChunksShareOneBudget() {
    SourceFacts facts = mock(SourceFacts.class);
    SourcePageReader reader = new SourcePageReader(facts, 1, 1);
    when(facts.topics(anyMap()))
        .thenReturn(
            map(
                "items",
                Collections.singletonList(map("topic_id", "T1")),
                "total",
                2,
                "page_no",
                1,
                "page_size",
                1));
    assertEquals(
        503, assertThrows(BusinessException.class, () -> reader.all(TOPICS, map())).status);
    assertEquals(1, reader.first(TOPICS, map(), 1).size());
    List<String> ids = new ArrayList<>();
    for (int i = 0; i < 501; i++) ids.add("A" + i);
    when(facts.accounts(anyMap()))
        .thenReturn(
            map("items", Collections.emptyList(), "total", 0, "page_no", 1, "page_size", 1));
    assertEquals(
        503, assertThrows(BusinessException.class, () -> reader.byIds(ACCOUNTS, ids, 1)).status);
    verify(facts, times(1)).accounts(anyMap());
  }

  @Test
  void ChineseAliasesWorkAndMarketingCannotReturnAnotherAccountsContent() {
    SourceFacts facts = mock(SourceFacts.class);
    SourcePageReader reader = new SourcePageReader(facts, 1, 2);
    when(facts.marketingContents(anyMap()))
        .thenReturn(
            map(
                "数据列表",
                Collections.singletonList(map("内容ID", "C1", "绑定账号ID", "A1")),
                "总数",
                1,
                "页码",
                1,
                "每页条数",
                1));
    assertEquals(1, reader.all(MARKETING_CONTENTS, map("account_id", "A1")).size());
    assertThrows(
        BusinessException.class, () -> reader.all(MARKETING_CONTENTS, map("account_id", "OTHER")));
  }
}
