package com.pab.aitmp.aiis.godp.planning.services.manual;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ManualPreviewRequest;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import java.time.*;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.dao.DuplicateKeyException;

/** Business authority: selection validation, durable task, formal results, idempotent commit. */
public class ManualPlanningService {
  private final ManualRepository repo;
  private final ManualPorts.Source source;
  private final ManualPorts.Computer computer;
  private final ManualPorts.Actor actor;

  public ManualPlanningService(
      ManualRepository repo,
      ManualPorts.Source source,
      ManualPorts.Computer computer,
      ManualPorts.Actor actor) {
    this.repo = repo;
    this.source = source;
    this.computer = computer;
    this.actor = RequestContexts.actor(actor);
  }

  static String now() {
    return Instant.now().toString();
  }

  static Map<String, Map<String, Object>> index(List<Map<String, Object>> rows, String key) {
    return rows.stream()
        .collect(Collectors.toMap(r -> text(r, key), r -> r, (a, b) -> a, LinkedHashMap::new));
  }

  public Set<String> unavailable(String date) {
    Set<String> out = new HashSet<>(source.historicalPlanned(date));
    out.addAll(repo.plannedAccountIds(date));
    return out;
  }

  public Map<String, Object> preview(ManualPreviewRequest input) {
    if (!"non_marketing".equals(input.content_mode) && input.content_mode != null)
      throw new BusinessException(422, "此入口只支持普通人工策划");
    if (new HashSet<>(input.account_ids).size() != input.account_ids.size())
      throw new BusinessException(422, "账号不能重复选择");
    if (input.target_count != null && input.target_count != input.account_ids.size())
      throw new BusinessException(422, "计划账号数量与所选账号不一致");
    Set<String> busy = new HashSet<>(source.historicalReserved(input.publish_date.toString()));
    busy.addAll(repo.reserved(input.publish_date.toString()));
    if (input.account_ids.stream().anyMatch(busy::contains))
      throw new BusinessException(409, "所选账号包含当日已人工策划或正在处理的账号");
    Map<String, Object> snapshot = source.snapshot(input.account_ids, input.topic_ids);
    Map<String, Map<String, Object>> accounts = index(rows(snapshot.get("accounts")), "account_id"),
        topics = index(rows(snapshot.get("topics")), "topic_id");
    if (!accounts.keySet().containsAll(input.account_ids))
      throw new BusinessException(422, "部分账号已不可参与策划，请重新选择");
    if (!topics.keySet().containsAll(input.topic_ids))
      throw new BusinessException(422, "部分选题不可用、已停用或过期");
    for (Map<String, Object> topic : topics.values()) {
      if (Boolean.TRUE.equals(topic.get("is_marketing")))
        throw new BusinessException(422, "非营销策划只能选择非营销选题");
      if (!TopicValidity.includes(topic, input.publish_date))
        throw new BusinessException(422, "投放日期不在选题有效期内：" + text(topic, "topic_title"));
    }
    String code = "JPREV-" + UUID.randomUUID();
    long time = System.currentTimeMillis();
    Map<String, Object> frozen =
        map(
            "accounts",
            input.account_ids.stream().map(accounts::get).collect(Collectors.toList()),
            "topics",
            input.topic_ids.stream().map(topics::get).collect(Collectors.toList()),
            "algorithm_version",
            snapshot.get("algorithm_version"));
    Map<String, Object> payload =
        map(
            "task_name",
            input.task_name.trim(),
            "publish_date",
            input.publish_date.toString(),
            "note",
            input.note,
            "input",
            frozen);
    repo.savePreview(code, write(payload), time + 1800000, actor.current(), time);
    return map(
        "preview_id",
        code,
        "task_name",
        input.task_name.trim(),
        "publish_date",
        input.publish_date.toString(),
        "expires_at",
        Instant.ofEpochMilli(time + 1800000).toString(),
        "items",
        Collections.emptyList(),
        "note",
        input.note);
  }

  public Map<String, Object> submit(String code) {
    Map<String, Object> accepted = repo.taskByPreview(code);
    if (accepted != null) return taskView(accepted);
    Map<String, Object> before = repo.previewByCode(code);
    if (before == null) throw new BusinessException(404, "策划预览不存在");
    Map<String, Object> prepared = read(text(before, "payload"));
    Set<String> oldBusy = source.historicalReserved(text(prepared, "publish_date"));
    if (rows(object(prepared.get("input")).get("accounts")).stream()
        .anyMatch(a -> oldBusy.contains(text(a, "account_id"))))
      throw new BusinessException(409, "所选账号存在当日人工策划任务，请重新选择");
    try {
      return repo.transaction(
          () -> {
            Map<String, Object> preview = repo.lockedPreview(code);
            if (preview == null) throw new BusinessException(404, "策划预览不存在");
            Map<String, Object> existing = repo.taskByPreview(code);
            if (existing != null) return taskView(existing);
            if (number(preview, "expires_at") < System.currentTimeMillis())
              throw new BusinessException(409, "策划预览已过期，请重新提交");
            Map<String, Object> payload = read(text(preview, "payload"));
            String taskCode = "JMAN-" + UUID.randomUUID();
            object(payload.get("input")).put("request_id", taskCode);
            payload.put("created_by", actor.current());
            payload.put("created_at", now());
            long time = System.currentTimeMillis();
            long id = repo.createTask(code, taskCode, write(payload), time);
            for (Map<String, Object> account : rows(object(payload.get("input")).get("accounts")))
              repo.reserve(text(payload, "publish_date"), text(account, "account_id"), id);
            return taskView(repo.taskById(id));
          });
    } catch (DuplicateKeyException conflict) {
      throw new BusinessException(409, "所选账号当日已有人工策划任务，请重新选择");
    }
  }

  /** Called by host scheduling; no Python business-table writes or cross-database transaction. */
  public void advance() {
    advance(10);
  }

  public void advance(int limit) {
    if(limit<1 || limit>500) throw new IllegalArgumentException("人工推进批量无效");
    String owner=UUID.randomUUID().toString();
    List<Map<String,Object>> pending=repo.pending();
    for (Map<String, Object> candidate : pending.subList(0,Math.min(limit,pending.size()))) {
      long id = number(candidate, "id");
      Map<String,Object> task=repo.claimTask(id,owner,System.currentTimeMillis(),120000);
      if(task==null) continue;
      try {
        Map<String, Object> payload = read(text(task, "payload"));
        Map<String, Object> receipt = computer.submit(object(payload.get("input")));
        if (!text(task, "task_code").equals(text(receipt, "request_id")))
          throw new BusinessException(502, "计算返回了不匹配的任务编号");
        if ("succeeded".equals(receipt.get("status")))
          repo.withClaim(id,owner,() -> complete(id, object(receipt.get("result"))));
        else if ("failed".equals(receipt.get("status")))
          repo.withClaim(id,owner,() -> fail(id, text(receipt, "error")));
        else if (Arrays.asList("pending", "running").contains(receipt.get("status")))
          repo.withClaim(id,owner,() -> repo.markComputing(id, System.currentTimeMillis()));
        else throw new BusinessException(502, "计算返回了未知状态");
      } catch (BusinessException invalid) {
        if (invalid.status == 409 || invalid.status == 422)
          repo.withClaim(id,owner,() -> fail(id, invalid.getMessage()));
        else {
          repo.withClaim(id,owner,() -> noteRetry(id));
          break;
        }
      } catch (RuntimeException transientFailure) {
        repo.withClaim(id,owner,() -> noteRetry(id));
        break; // Do not wait through the entire batch when the upstream is down.
      } finally {
        repo.releaseClaim(id,owner);
      }
    }
  }

  private void noteRetry(long id) {
    repo.noteRetry(id, "计算服务暂不可用，等待调度重试", System.currentTimeMillis());
  }

  /** Host-visible pass outcome; queued work and transient retry are not completion. */
  public Map<String, Object> advancePass() {
    return advancePass(10);
  }

  public Map<String,Object> advancePass(int limit) {
    advance(limit);
    List<Map<String, Object>> pending = repo.pending();
    boolean retry = pending.stream().anyMatch(t -> !text(t, "error_message").isEmpty());
    return map(
        "status",
        retry ? "retry_required" : "processed",
        "pending_in_scan",
        pending.size(),
        "business_complete",
        false,
        "has_more",
        false,
        "needs_next_tick",
        !pending.isEmpty(),
        "next_after_id",
        0L);
  }

  private void fail(long id, String reason) {
    repo.transaction(
        () -> {
          int changed =
              repo.markFailed(
                  id,
                  reason.substring(0, Math.min(reason.length(), 500)),
                  System.currentTimeMillis());
          if (changed > 0) repo.release(id);
          return null;
        });
  }

  public void complete(long id, Map<String, Object> result) {
    repo.transaction(
        () -> {
          Map<String, Object> task = repo.lockedTask(id);
          if (task == null || !Arrays.asList("pending", "computing").contains(task.get("status")))
            return null;
          Map<String, Object> payload = read(text(task, "payload")),
              input = object(payload.get("input"));
          Map<String, Map<String, Object>>
              accounts = index(rows(input.get("accounts")), "account_id"),
              topics = index(rows(input.get("topics")), "topic_id");
          List<Map<String, Object>> assignments = rows(result.get("items"));
          Set<String> seen = new HashSet<>();
          if (!text(input, "algorithm_version").equals(text(result, "algorithm_version")))
            throw new BusinessException(422, "计算配置版本不一致");
          for (Map<String, Object> row : assignments)
            if (!accounts.containsKey(text(row, "account_id"))
                || !topics.containsKey(text(row, "topic_id"))
                || !seen.add(text(row, "account_id")))
              throw new BusinessException(422, "计算结果包含未选择或重复的账号选题");
          if (!seen.equals(accounts.keySet())) throw new BusinessException(422, "计算结果缺少所选账号");
          String batchCode = "MAN-" + text(payload, "publish_date").replace("-", "") + "-J" + id;
          Map<String, Object> batch =
              map(
                  "id",
                  id,
                  "batch_code",
                  batchCode,
                  "task_name",
                  payload.get("task_name"),
                  "plan_type",
                  "manual",
                  "status",
                  "已完成",
                  "cycle_start",
                  payload.get("publish_date"),
                  "cycle_end",
                  payload.get("publish_date"),
                  "account_count",
                  accounts.size(),
                  "content_count",
                  assignments.size(),
                  "result_count",
                  accounts.size(),
                  "completed_count",
                  accounts.size(),
                  "failed_count",
                  0,
                  "topic_count",
                  assignments.stream().map(r -> r.get("topic_id")).distinct().count(),
                  "note",
                  payload.get("note"),
                  "created_at",
                  payload.get("created_at"),
                  "updated_at",
                  now(),
                  "planning_status",
                  "已完成",
                  "content_status",
                  "待生产",
                  "content_total_count",
                  assignments.size(),
                  "content_completed_count",
                  0,
                  "content_failed_count",
                  0,
                  "content_completed_account_count",
                  0);
          repo.saveBatch(id, write(batch), System.currentTimeMillis());
          for (Map<String, Object> row : assignments) {
            Map<String, Object> account = accounts.get(text(row, "account_id")),
                topic = topics.get(text(row, "topic_id"));
            Map<String, Object> item = new LinkedHashMap<>(topic);
            item.putAll(
                map(
                    "account_id",
                    account.get("account_id"),
                    "account_name",
                    account.get("account_name"),
                    "account_snapshot",
                    account,
                    "topic_snapshot",
                    topic,
                    "publish_date",
                    payload.get("publish_date"),
                    "slot_type",
                    "manual_extra",
                    "batch_id",
                    id,
                    "batch_code",
                    batchCode,
                    "task_name",
                    payload.get("task_name"),
                    "batch_created_at",
                    payload.get("created_at"),
                    "cycle_start",
                    payload.get("publish_date"),
                    "cycle_end",
                    payload.get("publish_date"),
                    "plan_type",
                    "manual",
                    "status",
                    "待生产",
                    "production_status",
                    "planned",
                    "slot_id",
                    "JSLOT-" + id + "-" + account.get("account_id"),
                    "publish_status",
                    "待发布",
                    "lifecycle_stage",
                    row.get("lifecycle_stage"),
                    "content_role",
                    "",
                    "allow_replace",
                    true,
                    "result_version",
                    1,
                    "replace_block_reason",
                    ""));
            repo.saveItem(
                id,
                text(item, "slot_id"),
                text(account, "account_id"),
                text(payload, "publish_date"),
                write(item));
          }
          repo.markCompleted(id, System.currentTimeMillis());
          return null;
        });
  }

  public Map<String, Object> taskView(Map<String, Object> task) {
    Map<String, Object> p = read(text(task, "payload")), input = object(p.get("input"));
    long id = number(task, "id");
    int count = rows(input.get("accounts")).size();
    boolean done = "completed".equals(task.get("status")),
        failed = "failed".equals(task.get("status"));
    Map<String, Object> batchRow = done ? repo.batchById(id) : null;
    Map<String, Object> progress = batchRow == null ? map() : read(text(batchRow, "payload"));
    return map(
        "id",
        id,
        "task_key",
        "java-manual:" + id,
        "task_code",
        task.get("task_code"),
        "preview_code",
        task.get("preview_code"),
        "task_name",
        p.get("task_name"),
        "publish_date",
        p.get("publish_date"),
        "planned_account_count",
        count,
        "result_count",
        done ? count : 0,
        "failure_count",
        failed ? count : 0,
        "topic_count",
        rows(input.get("topics")).stream().map(r -> r.get("topic_id")).distinct().count(),
        "status",
        done ? "已完成" : failed ? "执行失败" : "执行中",
        "planning_status",
        done ? "已完成" : failed ? "生成失败" : "生成中",
        "failure_reason",
        failed ? task.get("error_message") : "",
        "last_error",
        task.get("error_message"),
        "batch_id",
        done ? id : null,
        "batch_code",
        done ? "MAN-" + text(p, "publish_date").replace("-", "") + "-J" + id : "",
        "content_mode",
        "non_marketing",
        "content_status",
        done ? text(progress, "content_status") : "待生产",
        "content_failed_count",
        number(progress, "content_failed_count"),
        "content_completed_count",
        number(progress, "content_completed_count"),
        "content_completed_account_count",
        number(progress, "content_completed_account_count"),
        "content_total_count",
        done ? count : 0,
        "content_per_account",
        1,
        "allocation_count",
        0,
        "created_at",
        p.get("created_at"),
        "created_by",
        p.get("created_by"),
        "updated_at",
        Instant.ofEpochMilli(number(task, "updated_at")).toString());
  }
}
