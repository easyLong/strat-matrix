package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.context.RequestContexts;
import java.util.*;

/** Existing replacement behavior, with Java-owned version/state guards. */
public class ManualItemService {
  private final ManualRepository repo;
  private final ManualPorts.Source source;
  private final ManualPorts.Actor actor;

  public ManualItemService(ManualRepository r, ManualPorts.Source s, ManualPorts.Actor a) {
    repo = r;
    source = s;
    actor = RequestContexts.actor(a);
  }

  public List<Map<String, Object>> adjustments(long id) {
    return repo.adjustments(id);
  }

  public Map<String, Object> replace(long id, Map<String, Object> request) {
    String topicId = text(request, "new_topic_id");
    if (topicId.isEmpty()
        || topicId.length() > 64
        || number(request, "expected_version") < 1
        || text(request, "reason").length() > 500) throw new BusinessException(422, "换题参数无效");
    List<Map<String, Object>> topics =
        rows(
            source
                .snapshot(Collections.emptyList(), Collections.singletonList(topicId))
                .get("topics"));
    if (topics.size() != 1 || Boolean.TRUE.equals(topics.get(0).get("is_marketing")))
      throw new BusinessException(422, "请选择可用的非营销选题");
    Map<String, Object> topic = topics.get(0);
    return repo.transaction(
        () -> {
          Map<String, Object> record = repo.lockedItem(id);
          if (record == null) throw new BusinessException(404, "策划明细不存在");
          if (!"planned".equals(record.get("content_status")))
            throw new BusinessException(409, "仅待生产状态可以替换选题");
          if (number(record, "version") != number(request, "expected_version"))
            throw new BusinessException(409, "策划结果已更新，请重新打开");
          if (!TopicValidity.includes(topic, java.time.LocalDate.parse(text(record, "publish_date"))))
            throw new BusinessException(422, "投放日期不在选题有效期内");
          Map<String, Object> item = read(text(record, "payload"));
          if (topicId.equals(item.get("topic_id"))) throw new BusinessException(409, "请选择不同的选题");
          long version = number(record, "version") + 1;
          Map<String, Object> adjustment =
              map(
                  "item_id",
                  id,
                  "result_version",
                  version,
                  "adjustment_source",
                  "manual_replace",
                  "old_topic_id",
                  item.get("topic_id"),
                  "old_topic_title",
                  item.get("topic_title"),
                  "new_topic_id",
                  topicId,
                  "new_topic_title",
                  topic.get("topic_title"),
                  "reason",
                  text(request, "reason"),
                  "created_at",
                  ManualPlanningService.now(),
                  "created_by",
                  actor.current());
          for (String key :
              Arrays.asList(
                  "topic_id",
                  "topic_title",
                  "outline",
                  "content_type",
                  "topic_type",
                  "valid_from",
                  "valid_to",
                  "related_activity_id",
                  "related_activity",
                  "activity_organization",
                  "related_product_id",
                  "related_product",
                  "related_hotspot",
                  "labels")) item.put(key, topic.get(key));
          item.put("topic_snapshot", topic);
          item.put("result_version", version);
          item.put("updated_by", actor.current());
          item.put("id", id);
          repo.updateItemVersion(id, write(item), version);
          long adjustmentId = repo.saveAdjustment(id, write(adjustment));
          adjustment.put("id", adjustmentId);
          return map("item", item, "adjustment", adjustment);
        });
  }
}
