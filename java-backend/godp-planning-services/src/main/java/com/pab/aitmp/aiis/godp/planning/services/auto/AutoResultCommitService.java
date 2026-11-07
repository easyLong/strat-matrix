package com.pab.aitmp.aiis.godp.planning.services.auto;

import com.pab.aitmp.aiis.godp.planning.services.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.planning.entity.command.*;

import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;
import java.time.Instant;
import java.util.*;

/**
 * Bounded resumable writes; only the final short transaction publishes the batch and receipt.
 */
public final class AutoResultCommitService {
  public static final int MAX_ITEMS_PER_TICK = 500;
  private final AutoScheduleMapper tasks;
  private final ManualRepository results;
  private final AutoProposalValidator validator = new AutoProposalValidator();

  public AutoResultCommitService(AutoScheduleMapper tasks, ManualRepository results) {
    this.tasks = tasks;
    this.results = results;
  }

  public Map<String, Object> commit(long taskId, Map<String, Object> envelope, Instant instant) {
    // Validation, hashing and snapshot construction do not hold database locks.
    Map<String, Object> task = SqlRows.one(tasks.byId(taskId));
    if (task == null) throw new IllegalStateException("自动策划业务任务不存在");
    String hash = text(envelope, "proposal_hash");
    if (task.get("business_batch_id") != null) return existing(task, hash);
    if (!"计算中".equals(task.get("status"))) throw new IllegalStateException("业务任务不处于可提交状态");
    Map<String, Object> p = validator.validate(task, envelope);
    long batchId =
        taskId; // automatic task IDs use the reserved 2e12 range; manual tasks use 1e12.
    List<Map<String, Object>> slots = rows(p.get("slots"));
    Map<String, Object> accounts = object(p.get("accounts"));
    String start = text(p, "cycle_start"), end = text(p, "cycle_end");
    String code = "Auto-" + start.replace("-", ""), at = instant.toString();
    long topicCount =
        slots.stream()
            .map(s -> text(s, "topic_id"))
            .filter(s -> !s.isEmpty())
            .distinct()
            .count();
    Map<String, Object> batch =
        map(
            "id",
            batchId,
            "batch_code",
            code,
            "task_name",
            code,
            "plan_type",
            "auto",
            "cycle_start",
            start,
            "cycle_end",
            end,
            "status",
            "已完成",
            "planning_status",
            "已完成",
            "account_count",
            accounts.size(),
            "result_count",
            accounts.size(),
            "completed_count",
            accounts.size(),
            "failed_count",
            0,
            "content_count",
            slots.size(),
            "topic_count",
            topicCount,
            "content_status",
            "待生产",
            "content_total_count",
            slots.size(),
            "content_completed_count",
            0,
            "content_failed_count",
            0,
            "content_completed_account_count",
            0,
            "created_at",
            at,
            "updated_at",
            at,
            "pipeline_id",
            p.get("pipeline_id"),
            "proposal_hash",
            hash,
            "business_config_version",
            p.get("business_config_version"),
            "policy_id",
            p.get("policy_id"),
            "matching_task_id",
            p.get("matching_task_id"));
    List<Map<String, Object>> prepared = new ArrayList<>();
    Map<String, Integer> marketingCounts = new HashMap<>();
    int marketingMax = (int) number(object(p.get("business_config")), "marketing_max");
    for (Map<String, Object> slot : slots) {
      Map<String, Object> item = new LinkedHashMap<>(slot);
      String slotId = "JSLOT-" + batchId + "-" + text(slot, "slot_id");
      if (slotId.length() > 128) throw new IllegalStateException("业务槽位编号超长");
      boolean hotspot = "hotspot".equals(slot.get("slot_type"));
      Map<String, Object> account = object(accounts.get(text(slot, "account_id")));
      String accountId = text(slot, "account_id");
      boolean marketing =
          !hotspot
              && "转化".equals(slot.get("content_role"))
              && (Boolean.TRUE.equals(account.get("marketing_eligible"))
                  || !Boolean.FALSE.equals(account.get("marketing_eligible"))
                      && "认证".equals(account.get("account_type")))
              && marketingCounts.getOrDefault(accountId, 0) < marketingMax;
      if (marketing)
        marketingCounts.put(accountId, marketingCounts.getOrDefault(accountId, 0) + 1);
      item.putAll(
          map(
              "batch_id",
              batchId,
              "batch_code",
              code,
              "task_name",
              code,
              "cycle_start",
              start,
              "cycle_end",
              end,
              "batch_created_at",
              at,
              "plan_type",
              "auto",
              "account_name",
              account.get("account_name"),
              "account_snapshot",
              account,
              "status",
              hotspot ? "待定题" : "待生产",
              "production_status",
              hotspot ? "unassigned" : marketing ? "awaiting_market" : "planned",
              "allow_replace",
              !hotspot && !marketing,
              "result_version",
              1,
              "algorithm_slot_id",
              slot.get("slot_id"),
              "slot_id",
              slotId));
      if (hotspot)
        item.put(
            "hotspot_fallback",
            object(p.get("hotspot_fallbacks"))
                .get(text(slot, "account_id") + "|" + text(slot, "publish_date")));
      if (marketing) item.put("slot_type", "marketing_priority");
      prepared.add(item);
    }
    return persistPage(taskId, hash, batch, prepared, instant);
  }

  private Map<String, Object> existing(Map<String, Object> task, String hash) {
    if (!hash.equals(task.get("proposal_hash"))) throw new IllegalStateException("重复提交的提案指纹不同");
    if (results.batchById(number(task, "business_batch_id")) == null)
      throw new IllegalStateException("已提交业务批次丢失");
    return task;
  }

  private Map<String, Object> persistPage(long taskId, String hash, Map<String, Object> batch,
      List<Map<String, Object>> items, Instant instant) {
    return results.transaction(() -> {
      Map<String, Object> current = SqlRows.one(tasks.lockedById(taskId));
      if (current == null) throw new IllegalStateException("自动策划业务任务不存在");
      if (current.get("business_batch_id") != null) return existing(current, hash);
      if (!"计算中".equals(current.get("status"))) throw new IllegalStateException("业务任务不处于可提交状态");
      Map<String, Object> stage = results.lockedBatchWrite(taskId);
      if (stage == null) {
        results.saveStagingBatch(taskId, write(batch), instant.toEpochMilli());
        stage = results.lockedBatchWrite(taskId);
      }
      if (!"staging".equals(stage.get("write_state"))
          || !hash.equals(text(read(text(stage, "payload")), "proposal_hash")))
        throw new IllegalStateException("批次编号已占用或恢复提案指纹变化");
      int cursor = (int) number(stage, "write_cursor");
      if (cursor < 0 || cursor > items.size() || results.stagedItemCount(taskId) != cursor)
        throw new IllegalStateException("批次分批写入游标与明细数量不一致");
      int end = Math.min(items.size(), cursor + MAX_ITEMS_PER_TICK);
      String createdAt = Instant.ofEpochMilli(number(stage, "created_at")).toString();
      for (int i = cursor; i < end; i++) {
        Map<String, Object> item = items.get(i);
        item.put("batch_created_at", createdAt);
        results.saveItem(taskId, text(item, "slot_id"), text(item, "account_id"),
            text(item, "publish_date"), write(item), text(item, "production_status"));
      }
      results.advanceBatchWrite(taskId, end);
      if (end == items.size()) {
        if (results.stagedItemCount(taskId) != items.size()) throw new IllegalStateException("正式发布明细不完整");
        results.publishBatch(taskId);
        if (tasks.committed(taskId, taskId, hash, instant.toEpochMilli()) != 1)
          throw new IllegalStateException("业务任务提交状态已变化");
      }
      return SqlRows.one(tasks.lockedById(taskId));
    });
  }
}
