package com.stratmatrix.planning.manual;

import java.util.*;

/** Empty historical source used only by isolated business tests. */
class ManualTestTransition implements ManualPorts.Transition {
  public Map<String, Object> queryPage(String view, Map<String, Object> query) {
    return Json.map("items", Collections.emptyList(), "total", 0);
  }
  public long resultWatermark() { return 0; }
  public List<Map<String, Object>> latestOperations(List<Long> itemIds) { return Collections.emptyList(); }
  public List<Map<String, Object>> periodContext(Map<String, Object> query) { return Collections.emptyList(); }
  public List<Map<String, Object>> batches(int limit, String planType) { return Collections.emptyList(); }
  public Object batch(long id) { return null; }
  public Object replaceTopic(long id, Map<String, Object> request) { return null; }
  public List<Map<String, Object>> adjustments(long id) { return Collections.emptyList(); }
  public List<Map<String, Object>> replacementCandidates(long id) { return Collections.emptyList(); }
}
