package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.time.Instant;
import java.util.*;

/** Usage is derived from content-completed business rows, never from an obsolete AI counter. */
public final class TopicUsageService {
  private final ManualRepository repository;

  public TopicUsageService(ManualRepository repository) {
    this.repository = Objects.requireNonNull(repository);
  }

  public Map<String, Object> query(Map<String, Object> input) {
    for (String key : Arrays.asList("started_at", "ended_at", "统计开始时间", "统计结束时间"))
      if (input.get(key) != null) throw new BusinessException(422, "当前接口查询累计使用次数，不支持时间范围");
    Object raw = input.containsKey("topic_ids") ? input.get("topic_ids") : input.get("选题ID列表");
    if (!(raw instanceof List) || ((List<?>) raw).isEmpty() || ((List<?>) raw).size() > 500)
      throw new BusinessException(422, "选题ID数量须为1至500");
    List<String> ids = new ArrayList<>();
    for (Object value : (List<?>) raw) {
      if (!(value instanceof String)
          || ((String) value).trim().isEmpty()
          || !value.equals(((String) value).trim())
          || ((String) value).length() > 64
          || ids.contains(value)) throw new BusinessException(422, "选题ID须为非空且无重复的标识");
      ids.add((String) value);
    }
    Map<String, Long> counts = new HashMap<>();
    for (Map<String, Object> row : repository.completedTopicUsage(ids))
      counts.put(text(row, "topic_id"), number(row, "official_use_count"));
    List<Map<String, Object>> results = new ArrayList<>();
    for (String id : ids)
      results.add(map("topic_id", id, "official_use_count", counts.getOrDefault(id, 0L)));
    return map(
        "queried_at", Instant.now().toString(), "status", "success", "topic_results", results);
  }
}
