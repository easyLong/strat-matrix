package com.stratmatrix.planning.content;

import static com.stratmatrix.planning.manual.Json.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.*;

import com.stratmatrix.planning.source.SourceFacts;
import java.util.*;
import org.junit.jupiter.api.Test;

class ContentFactsPagingTest {
  @Test
  void approvedMarketingAllocationsReadAccountFactsOncePerBatchAndKeepContentOrder() {
    SourceFacts facts = mock(SourceFacts.class);
    when(facts.approvedDemandContents(anyMap()))
        .thenReturn(
            Arrays.asList(
                map("task_code", "M1", "content_id", "C1", "account_id", "A1"),
                map("task_code", "M1", "content_id", "C2", "account_id", "A2"),
                map("task_code", "M1", "content_id", "C3", "account_id", "A1")));
    when(facts.accounts(anyMap()))
        .thenAnswer(
            call -> {
              Map<String, Object> query = call.getArgument(0);
              assertEquals(Arrays.asList("A1", "A2"), query.get("account_ids"));
              return map(
                  "items",
                  Arrays.asList(
                      map("account_id", "A1", "nickname", "账号1"),
                      map("account_id", "A2", "nickname", "账号2")),
                  "total",
                  2,
                  "page_no",
                  query.get("page_no"),
                  "page_size",
                  query.get("page_size"));
            });
    List<Map<String, Object>> out = new ContentFactsAdapter(facts).approvedDemandContents("M1");
    assertEquals(3, out.size());
    assertEquals("C3", out.get(2).get("content_id"));
    assertTrue(out.get(0).containsKey("account_snapshot"));
    verify(facts, times(1)).accounts(anyMap());
  }
}
