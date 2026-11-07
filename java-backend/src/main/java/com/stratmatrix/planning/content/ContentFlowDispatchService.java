package com.stratmatrix.planning.content;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.config.BusinessPlanningConfigService;
import com.stratmatrix.planning.manual.*;
import java.time.*;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Host-triggered paged result-to-content-flow projection. No scheduler or producer threads. */
public class ContentFlowDispatchService {
  private static final Logger LOG = LoggerFactory.getLogger(ContentFlowDispatchService.class);
  private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");
  private final ManualRepository repo;
  private final BusinessPlanningConfigService config;
  private final ContentFlowWriter writer;

  public ContentFlowDispatchService(ManualRepository repo, BusinessPlanningConfigService config,
      ContentFlowWriter writer) {
    this.repo = Objects.requireNonNull(repo);
    this.config = Objects.requireNonNull(config);
    this.writer = Objects.requireNonNull(writer);
  }

  public Map<String, Object> scan(Instant now, int limit, long afterId) {
    if (now == null || limit < 1 || limit > 500 || afterId < 0)
      throw new BusinessException(422, "内容流水扫描参数无效");
    BusinessPlanningConfigService.Result rules = config.current();
    List<Map<String, Object>> candidates = repo.contentFlowCandidates(afterId, limit);
    Map<String, Integer> counts = new LinkedHashMap<>();
    List<Map<String, Object>> failures = new ArrayList<>();
    for (Map<String, Object> row : candidates) {
      String result;
      try {
        result = repo.transaction(() -> dispatch(row, rules, now));
      } catch (RuntimeException failure) {
        result = "failed";
        LOG.warn("内容流水写入待重试，策划明细ID={}，异常类别={}", number(row, "id"), failure.getClass().getSimpleName());
        failures.add(map("planning_item_id", number(row, "id"), "reason", "内容流水写入未确认，将在后续扫描重试"));
      }
      counts.put(result, counts.getOrDefault(result, 0) + 1);
    }
    boolean retry = counts.getOrDefault("failed", 0) > 0 || counts.getOrDefault("unconfigured", 0) > 0
        || counts.getOrDefault("incomplete", 0) > 0;
    return map("phase", "CONTENT_FLOW", "status", retry ? "retry_required" : "processed",
        "scanned", candidates.size(), "outcomes", counts, "failures", failures, "business_complete", false,
        "needs_next_tick", retry, "has_more", candidates.size() == limit,
        "next_after_id", candidates.isEmpty() ? afterId : number(candidates.get(candidates.size()-1), "id"));
  }

  private String dispatch(Map<String, Object> scanned, BusinessPlanningConfigService.Result rules, Instant now) {
    Map<String, Object> current = repo.lockedItem(number(scanned, "id"));
    if (current == null || !"planned".equals(current.get("content_status"))) return "changed";
    Map<String, Object> item = read(text(current, "payload"));
    if (number(object(item.get("content_flow_dispatch")), "result_version") == number(current, "version")
        && !text(object(item.get("content_flow_dispatch")), "flow_id").isEmpty()) return "already_written";
    // Existing approved content is a reference, not a new production request.
    if (!text(item, "content_id").isEmpty()) return "existing_content";
    if (text(current, "account_id").isEmpty() || text(current, "slot_id").isEmpty()
        || text(current, "publish_date").isEmpty() || text(item, "topic_id").isEmpty()) return "incomplete";
    String type = topicType(item);
    Integer lead = rules.config.content_production_lead_days == null ? null
        : rules.config.content_production_lead_days.get(type);
    if (lead == null) return "unconfigured";
    ContentFlowEntry entry = new ContentFlowEntry(current, type, lead, rules.version);
    if (entry.productionTime.toInstant().isAfter(now)) return "not_due";
    ContentFlowReceipt receipt = writer.upsert(entry);
    validateReceipt(entry, receipt);
    item.put("content_flow_dispatch", map("flow_id", receipt.flowId, "result_version", receipt.resultVersion,
        "production_time", receipt.productionTime.toString(), "production_lead_days", receipt.productionLeadDays,
        "configuration_version", receipt.configurationVersion, "written_at", Instant.now().toString()));
    // Queueing is not production; retain 待生产 and the ability to replace the topic.
    if (repo.updateItemContent(entry.planningItemId, "planned", write(item)) != 1)
      throw new BusinessException(409, "策划明细回执未保存");
    return receipt.outcome.name().toLowerCase(Locale.ROOT);
  }

  private static void validateReceipt(ContentFlowEntry entry, ContentFlowReceipt receipt) {
    if (receipt == null || receipt.flowId == null || receipt.flowId.trim().isEmpty() || receipt.flowId.length() > 128
        || receipt.planningItemId != entry.planningItemId || receipt.resultVersion != entry.resultVersion
        || receipt.outcome == null || receipt.productionTime == null
        || receipt.productionLeadDays < 0 || receipt.productionLeadDays > 365 || receipt.configurationVersion < 1)
      throw new BusinessException(502, "内容流水写入回执不符合约定");
    Instant expected = entry.publishDate.minusDays(receipt.productionLeadDays).atStartOfDay(BEIJING).toInstant();
    if (!expected.equals(receipt.productionTime.toInstant()))
      throw new BusinessException(502, "内容流水生产时间与投放日期不一致");
    if (receipt.outcome != ContentFlowReceipt.Outcome.ALREADY_PRESENT
        && (!entry.productionTime.toInstant().equals(receipt.productionTime.toInstant())
            || receipt.configurationVersion != entry.configurationVersion
            || receipt.productionLeadDays != entry.productionLeadDays))
      throw new BusinessException(502, "内容流水写入未采用本次配置");
  }

  static String topicType(Map<String, Object> item) {
    Map<String, Object> topic = object(item.get("topic_snapshot"));
    String type = text(item, "topic_type");
    if (type.isEmpty()) type = text(topic, "topic_type");
    if (Boolean.TRUE.equals(item.get("is_marketing")) || Boolean.TRUE.equals(topic.get("is_marketing"))
        || "营销".equals(type) || "marketing".equals(type)) return "marketing";
    if ("热点".equals(type) || "hotspot".equals(type)) return "hotspot";
    if ("普通".equals(type) || "normal".equals(type)) return "ordinary";
    return "hotspot".equals(item.get("slot_type")) ? "hotspot" : "ordinary";
  }
}
