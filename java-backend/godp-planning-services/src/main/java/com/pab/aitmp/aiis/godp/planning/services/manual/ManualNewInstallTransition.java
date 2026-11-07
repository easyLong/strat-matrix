package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Closes the old Python history bridge. Use for a new installation or after historical data has
 * been imported and PlanningReadQueries serves the business database. Missing local results fail
 * explicitly instead of silently falling back to the old writer.
 */
public final class ManualNewInstallTransition implements ManualPorts.Transition {
  @Override
  public Map<String, Object> queryPage(String view, Map<String, Object> query) {
    return Json.map("items", Collections.emptyList(), "total", 0);
  }

  @Override
  public long resultWatermark() {
    return 0;
  }

  @Override
  public List<Map<String, Object>> latestOperations(List<Long> itemIds) {
    return Collections.emptyList();
  }

  @Override
  public List<Map<String, Object>> periodContext(Map<String, Object> query) {
    return Collections.emptyList();
  }

  @Override
  public List<Map<String, Object>> batches(int limit, String planType) {
    return Collections.emptyList();
  }

  @Override
  public Object batch(long id) {
    throw missingHistory();
  }

  @Override
  public Object replaceTopic(long id, Map<String, Object> request) {
    throw missingHistory();
  }

  @Override
  public List<Map<String, Object>> adjustments(long id) {
    throw missingHistory();
  }

  @Override
  public List<Map<String, Object>> replacementCandidates(long id) {
    throw missingHistory();
  }

  private BusinessException missingHistory() {
    return new BusinessException(404, "历史策划记录不存在");
  }
}
