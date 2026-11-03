package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.*;

import java.util.*;
import java.util.stream.Collectors;

/** Projects content-owned observations into Java business results; never produces content. */
public class ManualContentStatusService {
  private final ManualRepository repo;
  private final ManualPorts.ContentStatusSource source;

  public ManualContentStatusService(ManualRepository repo, ManualPorts.ContentStatusSource source) {
    this.repo = repo;
    this.source = source;
  }

  public Map<String, Object> reconcile(int limit) {
    return reconcile(limit, 0);
  }

  public Map<String, Object> reconcile(int limit, long afterId) {
    if (limit < 1 || limit > 200) throw new BusinessException(422, "单次查询数量须为1至200");
    if (afterId < 0) throw new BusinessException(422, "游标无效");
    List<Map<String, Object>> pending = repo.pendingItems(afterId, limit);
    long nextAfterId = pending.isEmpty() ? afterId : number(pending.get(pending.size() - 1), "id");
    List<ManualPorts.ContentCandidate> candidates = new ArrayList<>();
    Map<Long, ManualPorts.ContentCandidate> expected = new HashMap<>();
    for (Map<String, Object> row : pending) {
      Map<String, Object> item = read(text(row, "payload"));
      if (text(item, "topic_id").isEmpty()) continue;
      ManualPorts.ContentCandidate candidate =
          new ManualPorts.ContentCandidate(
              number(row, "id"),
              text(item, "slot_id"),
              (int) number(row, "version"),
              text(item, "topic_id"));
      candidates.add(candidate);
      expected.put(candidate.itemId, candidate);
    }
    if (candidates.isEmpty())
      return map(
          "status",
          "idle",
          "scanned",
          0,
          "applied",
          0,
          "stale",
          0,
          "next_after_id",
          nextAfterId,
          "has_more",
          pending.size() == limit);
    List<ManualPorts.ContentObservation> observations = source.query(candidates);
    if (observations == null) throw new BusinessException(502, "内容状态查询未返回结果");
    Set<Long> seen = new HashSet<>();
    for (ManualPorts.ContentObservation observation : observations) {
      if (observation == null
          || !expected.containsKey(observation.itemId)
          || !seen.add(observation.itemId)
          || observation.updatedAtMillis <= 0
          || !Arrays.asList("待生产", "生产中", "已完成", "生产失败").contains(observation.status)
          || ("已完成".equals(observation.status)
              && (observation.contentId == null || observation.contentId.isEmpty()))
          || (observation.contentId != null && observation.contentId.length() > 64)
          || (observation.productionTaskId != null && observation.productionTaskId.length() > 64)
          || (observation.error != null && observation.error.length() > 500))
        throw new BusinessException(502, "内容状态返回不符合约定");
    }
    int applied = 0, stale = 0;
    for (ManualPorts.ContentObservation observation : observations) {
      if (apply(observation, expected.get(observation.itemId))) applied++;
      else stale++;
    }
    return map(
        "status",
        "reconciled",
        "scanned",
        candidates.size(),
        "applied",
        applied,
        "stale",
        stale,
        "next_after_id",
        nextAfterId,
        "has_more",
        pending.size() == limit);
  }

  private boolean apply(
      ManualPorts.ContentObservation observation, ManualPorts.ContentCandidate candidate) {
    return repo.transaction(
        () -> {
          Map<String, Object> row = repo.lockedItem(candidate.itemId);
          if (row == null
              || number(row, "version") != candidate.version
              || observation.version != candidate.version) return false;
          Map<String, Object> item = read(text(row, "payload"));
          if (!candidate.topicId.equals(text(item, "topic_id"))
              || !candidate.slotId.equals(text(item, "slot_id"))) return false;
          String previous = text(row, "content_status");
          String next = state(observation.status);
          if ("generated".equals(previous)
              || ("ready".equals(previous) && "planned".equals(next))
              || observation.updatedAtMillis <= number(item, "production_reported_at"))
            return false;
          item.put("production_status", next);
          item.put("status", observation.status);
          item.put("content_id", observation.contentId == null ? "" : observation.contentId);
          item.put(
              "production_task_id",
              observation.productionTaskId == null ? "" : observation.productionTaskId);
          item.put("production_reported_at", observation.updatedAtMillis);
          item.put("production_error", observation.error == null ? "" : observation.error);
          item.put("allow_replace", "planned".equals(next));
          item.put("replace_block_reason", "planned".equals(next) ? "" : "内容已进入生产，不可替换选题");
          repo.updateItemContent(candidate.itemId, next, write(item));
          refreshBatch(number(row, "batch_id"));
          return true;
        });
  }

  public void refreshBatch(long batchId) {
    Map<String, Object> row = repo.lockedBatch(batchId);
    if (row == null) throw new BusinessException(500, "策划批次与明细不一致");
    List<Map<String, Object>> items = repo.batchItemStatuses(batchId);
    long completed =
        items.stream().filter(i -> "generated".equals(i.get("content_status"))).count();
    long failed = items.stream().filter(i -> "failed".equals(i.get("content_status"))).count();
    long producing = items.stream().filter(i -> "ready".equals(i.get("content_status"))).count();
    Map<String, List<Map<String, Object>>> byAccount =
        items.stream().collect(Collectors.groupingBy(i -> text(i, "account_id")));
    long completedAccounts =
        byAccount.values().stream()
            .filter(
                accountItems ->
                    accountItems.stream()
                        .allMatch(i -> "generated".equals(i.get("content_status"))))
            .count();
    Map<String, Object> batch = read(text(row, "payload"));
    int total = items.size();
    String status =
        completed == total
            ? "已完成"
            : failed > 0 && completed + failed == total
                ? "生成失败"
                : completed + failed + producing > 0 ? "生成中" : "待生产";
    batch.put("content_status", status);
    batch.put(
        "topic_count",
        items.stream()
            .map(i -> text(read(text(i, "payload")), "topic_id"))
            .filter(t -> !t.isEmpty())
            .distinct()
            .count());
    batch.put("content_total_count", total);
    batch.put("content_completed_count", completed);
    batch.put("content_failed_count", failed);
    batch.put("content_completed_account_count", completedAccounts);
    batch.put("updated_at", ManualPlanningService.now());
    repo.updateBatch(batchId, write(batch));
  }

  private static String state(String status) {
    switch (status) {
      case "待生产":
        return "planned";
      case "生产中":
        return "ready";
      case "已完成":
        return "generated";
      case "生产失败":
        return "failed";
      default:
        throw new BusinessException(502, "未知内容状态");
    }
  }
}
