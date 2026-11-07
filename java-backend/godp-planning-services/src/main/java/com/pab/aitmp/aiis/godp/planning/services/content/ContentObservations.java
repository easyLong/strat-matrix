package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import java.time.OffsetDateTime;
import java.util.*;

/** Map explicit content-owned observations; never starts production or manufactures success. */
public class ContentObservations {
  private final SourceFacts facts;

  public ContentObservations(SourceFacts facts) {
    this.facts = facts;
  }

  private static Object field(Map<String, Object> row, String key, String alias) {
    return row.containsKey(alias) ? row.get(alias) : row.get(key);
  }

  private static String string(Map<String, Object> row, String key, String alias) {
    Object value = field(row, key, alias);
    return value == null ? "" : value.toString();
  }

  private static long updated(Map<String, Object> row) {
    try {
      return OffsetDateTime.parse(string(row, "updated_at", "状态更新时间")).toInstant().toEpochMilli();
    } catch (RuntimeException invalid) {
      throw new BusinessException(503, "模拟内容状态更新时间无效");
    }
  }

  public List<ManualPorts.ContentObservation> content(
      List<ManualPorts.ContentCandidate> candidates) {
    if (candidates.isEmpty()) return Collections.emptyList();
    Set<String> slotIds = new HashSet<>();
    for (ManualPorts.ContentCandidate c : candidates) slotIds.add(c.slotId);
    List<ManualPorts.ContentObservation> result = new ArrayList<>();
    for (Map<String, Object> row :
        rows(facts.productionStatus(map("slot_ids", new ArrayList<>(slotIds))))) {
      List<ManualPorts.ContentCandidate> matches = new ArrayList<>();
      for (ManualPorts.ContentCandidate candidate : candidates)
        if (candidate.slotId.equals(text(row, "slot_id"))
            && candidate.version == number(row, "version")) matches.add(candidate);
      if (matches.isEmpty()) continue; // Stale versions cannot update a current result.
      if (matches.size() > 1) throw new BusinessException(503, "模拟内容状态无法唯一关联策划明细");
      ManualPorts.ContentCandidate c = matches.get(0);
      result.add(
          new ManualPorts.ContentObservation(
              c.itemId,
              (int) number(row, "version"),
              string(row, "status", "内容状态"),
              string(row, "content_id", "内容ID"),
              updated(row),
              string(row, "production_task_id", "生产任务ID"),
              string(row, "error", "失败原因")));
    }
    return result;
  }

  public List<ManualPorts.MarketingObservation> marketing(List<String> codes) {
    if (codes.isEmpty()) return Collections.emptyList();
    List<ManualPorts.MarketingObservation> result = new ArrayList<>();
    for (Map<String, Object> row : rows(facts.marketingStatus(map("task_codes", codes)))) {
      result.add(
          new ManualPorts.MarketingObservation(
              text(row, "task_code"),
              string(row, "status", "内容状态"),
              ((Number) field(row, "account_count", "已分配账号数")).intValue(),
              ((Number) field(row, "completed_count", "完成数")).intValue(),
              ((Number) field(row, "failed_count", "失败数")).intValue(),
              updated(row)));
    }
    return result;
  }
}
