package com.stratmatrix.planning.manual;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class HostSourceAdapterTest {
  @Test
  void delegatesEachHostCapabilityWithoutLosingReservationSemantics() {
    ManualPorts.AccountFacts accounts = new ManualPorts.AccountFacts() {
      public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
        return Collections.singletonList(Json.map("limit", limit, "include_disabled", includeDisabled));
      }
      public Map<String, Object> sourceAccounts(List<String> ids) {
        return Json.map("accounts", ids);
      }
    };
    ManualPorts.TopicFacts topics = new ManualPorts.TopicFacts() {
      public List<Map<String, Object>> topicCandidates(int limit) {
        return Collections.singletonList(Json.map("limit", limit));
      }
      public Map<String, Object> topicDetail(String id, String type) {
        return Json.map("topic_id", id, "topic_type", type);
      }
    };
    ManualPorts.SnapshotFacts snapshots = (accountIds, topicIds) ->
        Json.map("accounts", accountIds, "topics", topicIds, "algorithm_version", "v2");
    ManualPorts.HistoricalEligibility history = new ManualPorts.HistoricalEligibility() {
      public Set<String> historicalPlanned(String date) { return Collections.singleton("A1"); }
      public Set<String> historicalReserved(String date) {
        return new HashSet<>(Arrays.asList("A1", "A2"));
      }
    };
    ManualPorts.Source source = new HostSourceAdapter(accounts, topics, snapshots, history);

    assertEquals(20, source.accountOptions(20, true).get(0).get("limit"));
    assertEquals(true, source.accountOptions(20, true).get(0).get("include_disabled"));
    assertEquals(Collections.singletonList("A3"), source.sourceAccounts(Collections.singletonList("A3")).get("accounts"));
    assertEquals(5, source.topicCandidates(5).get(0).get("limit"));
    assertEquals("marketing", source.topicDetail("T1", "marketing").get("topic_type"));
    assertEquals("v2", source.snapshot(Collections.singletonList("A3"), Collections.singletonList("T1")).get("algorithm_version"));
    assertEquals(Collections.singleton("A1"), source.historicalPlanned("2026-11-02"));
    assertTrue(source.historicalReserved("2026-11-02").contains("A2"));
    assertThrows(NullPointerException.class, () -> new HostSourceAdapter(accounts, topics, snapshots, null));
  }
}
