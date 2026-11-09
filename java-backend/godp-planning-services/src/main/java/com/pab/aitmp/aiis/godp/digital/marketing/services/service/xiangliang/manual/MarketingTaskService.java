package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.MarketingTaskRequest;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context.RequestContexts;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;

/** Business authority for undated manual marketing demand. Content allocation is external. */
public class MarketingTaskService {
  private final ManualRepository repo;
  private final ManualPorts.Source source;
  private final ManualPorts.Actor actor;
  private final ManualPorts.MarketingStatusSource statusSource;

  public MarketingTaskService(
      ManualRepository repo,
      ManualPorts.Source source,
      ManualPorts.Actor actor,
      ManualPorts.MarketingStatusSource statusSource) {
    this.repo = repo;
    this.source = source;
    this.actor = RequestContexts.actor(actor);
    this.statusSource = statusSource;
  }

  public Map<String, Object> create(MarketingTaskRequest request) {
    if (request == null
        || request.request_id == null
        || request.task_name == null
        || request.task_name.trim().isEmpty()
        || request.task_name.trim().length() > 120
        || request.topic_id == null
        || request.topic_id.trim().isEmpty()
        || request.topic_id.trim().length() > 64
        || request.allocation_count == null
        || request.allocation_count < 1
        || request.allocation_count > 1000)
      throw new BusinessException(422, "请填写有效的任务名称、选题和生成内容数量");
    String name = request.task_name.trim(), topicId = request.topic_id.trim();
    String requestId = request.request_id.toString();
    String fingerprint =
        hash(
            write(
                map(
                    "task_name",
                    name,
                    "topic_id",
                    topicId,
                    "allocation_count",
                    request.allocation_count)));
    Map<String, Object> existing = repo.marketingByRequest(requestId);
    if (existing != null) return replay(existing, fingerprint);
    Map<String, Object> sourceData =
        source.snapshot(Collections.emptyList(), Collections.singletonList(topicId));
    List<Map<String, Object>> topics = rows(sourceData.get("topics"));
    if (topics.size() != 1 || !topicId.equals(text(topics.get(0), "topic_id")))
      throw new BusinessException(409, "选题已停用或不存在，请重新选择");
    Map<String, Object> topic = topics.get(0);
    if (!Boolean.TRUE.equals(topic.get("is_marketing")))
      throw new BusinessException(422, "营销策划只能选择营销选题");
    if (!TopicValidity.includes(topic, TopicValidity.today()))
      throw new BusinessException(422, "当前日期不在营销选题有效期内，请重新选择");
    long now = System.currentTimeMillis();
    Map<String, Object> values =
        map(
            "taskCode",
            "JMAN-MKT-" + UUID.randomUUID(),
            "requestId",
            requestId,
            "requestHash",
            fingerprint,
            "taskName",
            name,
            "topicId",
            topicId,
            "allocationCount",
            request.allocation_count,
            "topicSnapshot",
            write(topic),
            "createdBy",
            actor.current(),
            "createdAt",
            now);
    try {
      return repo.transaction(
          () -> {
            Map<String, Object> previous = repo.marketingByRequest(requestId);
            if (previous != null) return replay(previous, fingerprint);
            repo.saveMarketingTask(values);
            return summary(repo.marketingByCode(text(values, "taskCode")));
          });
    } catch (DuplicateKeyException conflict) {
      Map<String, Object> previous = repo.marketingByRequest(requestId);
      if (previous != null) return replay(previous, fingerprint);
      throw new BusinessException(409, "营销任务编号冲突，请重新提交");
    }
  }

  private Map<String, Object> replay(Map<String, Object> row, String fingerprint) {
    if (!fingerprint.equals(text(row, "request_hash")))
      throw new BusinessException(409, "该提交标识已用于其他任务，请重新创建");
    return summary(row);
  }

  public Map<String, Object> detail(String code) {
    Map<String, Object> row = repo.marketingByCode(code);
    if (row == null) throw new BusinessException(404, "营销任务不存在");
    return map(
        "task",
        summary(row),
        "accounts",
        Collections.emptyList(),
        "topics",
        Collections.singletonList(read(text(row, "topic_snapshot_json"))));
  }

  public List<Map<String, Object>> all() {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> row : repo.marketingTasks()) out.add(summary(row));
    return out;
  }

  public Map<String, Object> reconcile(int limit, long afterId) {
    if (limit < 1 || limit > 500 || afterId < 0) throw new BusinessException(422, "营销状态扫描范围无效");
    List<Map<String, Object>> pending = repo.pendingMarketingTasks(afterId, limit);
    if (pending.isEmpty()) return map("applied", 0, "next_after_id", afterId, "has_more", false);
    Set<String> expected = new HashSet<>();
    for (Map<String, Object> row : pending) expected.add(text(row, "task_code"));
    List<ManualPorts.MarketingObservation> observations =
        statusSource.query(new ArrayList<>(expected));
    if (observations == null) throw new BusinessException(502, "内容方未返回营销状态");
    Set<String> seen = new HashSet<>();
    for (ManualPorts.MarketingObservation observed : observations)
      if (observed == null || !expected.contains(observed.taskCode) || !seen.add(observed.taskCode))
        throw new BusinessException(502, "内容方返回了范围外或重复的营销任务");
    int applied = 0;
    for (ManualPorts.MarketingObservation observed : observations) if (apply(observed)) applied++;
    return map(
        "applied",
        applied,
        "next_after_id",
        number(pending.get(pending.size() - 1), "id"),
        "has_more",
        pending.size() == limit);
  }

  private boolean apply(ManualPorts.MarketingObservation observed) {
    return repo.transaction(
        () -> {
          Map<String, Object> current = repo.lockedMarketingTask(observed.taskCode);
          if (current == null
              || "已完成".equals(current.get("status"))
              || (current.get("production_reported_at") != null
                  && observed.updatedAtMillis <= number(current, "production_reported_at")))
            return false;
          long total = number(current, "allocation_count");
          if (!Arrays.asList("待分配", "待生产", "生产中", "生产失败", "已完成").contains(observed.status)
              || observed.updatedAtMillis < 1
              || observed.accountCount < 0
              || observed.completedCount < 0
              || observed.failedCount < 0
              || observed.accountCount > total
              || (long) observed.completedCount + observed.failedCount > total
              || observed.completedCount < number(current, "content_completed_count")
              // Failed is the current unresolved count; it can fall after content-side retry.
              || ("已完成".equals(observed.status)
                  && (observed.completedCount != total || observed.failedCount != 0)))
            throw new BusinessException(502, "内容方营销生产数量或状态不一致");
          repo.updateMarketingProgress(
              number(current, "id"),
              observed.status,
              observed.accountCount,
              observed.completedCount,
              observed.failedCount,
              observed.updatedAtMillis);
          return true;
        });
  }

  public static Map<String, Object> summary(Map<String, Object> row) {
    long id = number(row, "id"), total = number(row, "allocation_count");
    boolean done = "已完成".equals(row.get("status"));
    return map(
        "id",
        -id,
        "task_code",
        row.get("task_code"),
        "preview_code",
        "",
        "task_name",
        row.get("task_name"),
        "batch_code",
        row.get("task_code"),
        "publish_date",
        null,
        "planned_account_count",
        number(row, "account_count"),
        "result_count",
        0,
        "failure_count",
        0,
        "topic_count",
        1,
        "status",
        row.get("status"),
        "planning_status",
        row.get("status"),
        "content_status",
        row.get("status"),
        "content_failed_count",
        number(row, "content_failed_count"),
        "content_completed_count",
        done ? total : number(row, "content_completed_count"),
        "content_total_count",
        total,
        "content_completed_account_count",
        done ? number(row, "account_count") : 0,
        "failure_reason",
        "",
        "batch_id",
        row.get("batch_id"),
        "last_error",
        "",
        "created_at",
        Instant.ofEpochMilli(number(row, "created_at")).toString(),
        "created_by",
        row.get("created_by"),
        "updated_at",
        Instant.ofEpochMilli(number(row, "updated_at")).toString(),
        "content_mode",
        "marketing",
        "content_per_account",
        0,
        "allocation_count",
        total,
        "task_key",
        "marketing:" + id);
  }

  private static String hash(String value) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
      StringBuilder out = new StringBuilder();
      for (byte b : digest) out.append(String.format("%02x", b & 0xff));
      return out.toString();
    } catch (java.security.NoSuchAlgorithmException impossible) {
      throw new IllegalStateException(impossible);
    }
  }
}
