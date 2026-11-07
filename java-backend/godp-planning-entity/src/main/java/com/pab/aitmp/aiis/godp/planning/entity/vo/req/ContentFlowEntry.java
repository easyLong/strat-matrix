package com.pab.aitmp.aiis.godp.planning.entity.vo.req;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.time.*;
import java.util.*;

/** Input for the host content-flow table; it does not start content generation. */
public final class ContentFlowEntry {
  public final long planningItemId;
  public final long batchId;
  public final int resultVersion;
  public final String slotId;
  public final String accountId;
  public final String topicId;
  public final String topicType;
  public final LocalDate publishDate;
  public final int productionLeadDays;
  public final int configurationVersion;
  public final OffsetDateTime productionTime;
  public final Map<String, Object> planningResult;
  public final Map<String, Object> accountInfo;
  public final Map<String, Object> topicInfo;

  public ContentFlowEntry(Map<String, Object> row, String type, int leadDays, int configVersion) {
    Map<String, Object> item = read(text(row, "payload"));
    item.remove("content_flow_dispatch");
    planningItemId = number(row, "id");
    batchId = number(row, "batch_id");
    resultVersion = (int) number(row, "version");
    slotId = text(row, "slot_id");
    accountId = text(row, "account_id");
    topicId = text(item, "topic_id");
    topicType = type;
    publishDate = LocalDate.parse(text(row, "publish_date"));
    productionLeadDays = leadDays;
    configurationVersion = configVersion;
    productionTime = publishDate.minusDays(leadDays).atStartOfDay(ZoneId.of("Asia/Shanghai")).toOffsetDateTime();
    // Identity/version from the locked row are authoritative over old payload fields.
    item.putAll(map("id", planningItemId, "batch_id", batchId, "slot_id", slotId,
        "account_id", accountId, "publish_date", publishDate.toString(), "result_version", resultVersion));
    planningResult = Collections.unmodifiableMap(item);
    Map<String, Object> account = new LinkedHashMap<>(object(item.get("account_snapshot")));
    account.put("account_id", accountId);
    if (!account.containsKey("account_name")) account.put("account_name", item.get("account_name"));
    accountInfo = Collections.unmodifiableMap(account);
    Map<String, Object> topic = new LinkedHashMap<>(object(item.get("topic_snapshot")));
    for (String key : Arrays.asList("topic_id", "topic_title", "title", "outline", "content_type",
        "topic_type", "is_marketing", "valid_from", "valid_to", "labels", "content_agent",
        "related_activity_id", "related_activity", "activity_organization", "related_product_id", "related_product"))
      if (!topic.containsKey(key) && item.containsKey(key)) topic.put(key, item.get(key));
    topic.put("topic_id", topicId);
    topicInfo = Collections.unmodifiableMap(topic);
  }

  public String idempotencyKey() {
    return "PLANNING-" + planningItemId + "-V" + resultVersion;
  }

  public Map<String, Object> toMap() {
    return map("idempotency_key", idempotencyKey(), "planning_item_id", planningItemId,
        "result_version", resultVersion, "batch_id", batchId, "slot_id", slotId,
        "account_id", accountId, "topic_id", topicId, "topic_type", topicType,
        "publish_date", publishDate.toString(), "production_time", productionTime.toString(),
        "production_lead_days", productionLeadDays, "configuration_version", configurationVersion,
        "planning_result", planningResult, "account_info", accountInfo, "topic_info", topicInfo);
  }
}
