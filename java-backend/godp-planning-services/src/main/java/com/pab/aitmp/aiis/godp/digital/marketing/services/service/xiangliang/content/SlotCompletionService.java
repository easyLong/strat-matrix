package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.SqlRows;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualContentStatusService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.*;

import java.time.*;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;

/**
 * Host-triggered T-1 hotspot decisions and approved marketing references. No content generation.
 */
public final class SlotCompletionService {
  private final SlotCompletionMapper slots;
  private final ManualRepository repo;
  private final PlanningContentPort source;
  private final ManualContentStatusService progress;

  public SlotCompletionService(
      SlotCompletionMapper slots,
      ManualRepository repo,
      PlanningContentPort source,
      ManualContentStatusService progress) {
    this.slots = slots;
    this.repo = repo;
    this.source = source;
    this.progress = progress;
  }

  public static LocalDate hotspotPublishDate(Instant now) {
    return now.atZone(ZoneId.of("Asia/Shanghai")).toLocalDate().plusDays(1);
  }

  public Map<String, Object> hotspots(Instant now, int limit, long after) {
    checkScan(limit, after);
    List<Map<String, Object>> pending =
        SqlRows.list(slots.hotspotsOnDate(hotspotPublishDate(now).toString(), after, limit));
    if (pending.isEmpty()) return map("applied", 0, "next_after_id", after, "has_more", false);
    List<Map<String, Object>> candidates = source.hotspots(now);
    if (candidates == null) throw new BusinessException(502, "热点查询未返回有效列表");
    List<Map<String, Object>> ordered = new ArrayList<>(candidates);
    ordered.sort(Comparator.comparing(t -> text(t, "topic_id")));
    int applied = 0;
    for (Map<String, Object> row : pending) {
      boolean changed =
          repo.transaction(
              () -> {
                Map<String, Object> current = repo.lockedItem(number(row, "id"));
                if (current == null
                    || !"unassigned".equals(current.get("content_status"))
                    || number(current, "version") != number(row, "version")) return false;
                Map<String, Object> item = read(text(current, "payload"));
                List<Map<String, Object>> choices = new ArrayList<>(ordered);
                Collections.shuffle(
                    choices,
                    new Random((text(item, "publish_date") + text(item, "slot_id")).hashCode()));
                Map<String, Object> selected = null;
                for (Map<String, Object> topic : choices) {
                  if (text(topic, "topic_id").isEmpty()
                      || text(topic, "title").isEmpty()
                      || Boolean.FALSE.equals(topic.get("available"))) continue;
                  if (!validOnDate(topic, LocalDate.parse(text(item, "publish_date")))) continue;
                  if (claim(
                      "hotspot",
                      text(item, "publish_date") + "|" + text(topic, "topic_id"),
                      number(current, "id"))) {
                    selected = topic;
                    break;
                  }
                }
                boolean fallback = selected == null;
                if (fallback) selected = object(item.get("hotspot_fallback"));
                if (text(selected, "topic_id").isEmpty() || text(selected, "title").isEmpty())
                  throw new BusinessException(409, "热点槽位缺少冻结普通兜底，等待处理");
                item.putAll(
                    map(
                        "topic_id",
                        selected.get("topic_id"),
                        "topic_title",
                        selected.get("title"),
                        "outline",
                        selected.get("outline"),
                        "content_type",
                        selected.get("content_type"),
                        "topic_type",
                        fallback ? "普通" : "热点",
                        "status",
                        "待生产",
                        "production_status",
                        "planned"));
                item.put("topic_snapshot", new LinkedHashMap<>(selected));
                complete(current, item, "planned", fallback ? "合法热点不足，采用冻结普通选题兜底" : "热点T-1定题", now);
                return true;
              });
      if (changed) applied++;
    }
    return map(
        "applied",
        applied,
        "next_after_id",
        number(pending.get(pending.size() - 1), "id"),
        "has_more",
        pending.size() == limit);
  }

  private static boolean validOnDate(Map<String, Object> topic, LocalDate date) {
    String from = text(topic, "valid_from"), to = text(topic, "valid_to");
    try {
      ZoneId zone = ZoneId.of("Asia/Shanghai");
      Instant start = date.atStartOfDay(zone).toInstant(),
          end = date.plusDays(1).atStartOfDay(zone).toInstant();
      // There is no publish-time field: a topic may be valid during any part of the publish day.
      return (from.isEmpty() || !boundary(from, false).isAfter(boundary(to, true)))
          && (from.isEmpty() || boundary(from, false).isBefore(end))
          && (to.isEmpty() || !boundary(to, true).isBefore(start));
    } catch (RuntimeException invalid) {
      throw new BusinessException(502, "热点选题有效期格式无效");
    }
  }

  private static Instant boundary(String value, boolean end) {
    if (value.isEmpty()) return end ? Instant.MAX : Instant.MIN;
    ZoneId zone = ZoneId.of("Asia/Shanghai");
    if (value.length() == 10) {
      LocalDate day = LocalDate.parse(value);
      return end
          ? day.plusDays(1).atStartOfDay(zone).toInstant().minusNanos(1)
          : day.atStartOfDay(zone).toInstant();
    }
    try {
      return OffsetDateTime.parse(value).toInstant();
    } catch (java.time.format.DateTimeParseException local) {
      return LocalDateTime.parse(value).atZone(zone).toInstant();
    }
  }

  public Map<String, Object> marketing(Instant now, int limit, long after) {
    checkScan(limit, after);
    List<Map<String, Object>> pending = SqlRows.list(slots.marketingSlots(after, limit));
    int applied = 0;
    for (Map<String, Object> row : pending) {
      Map<String, Object> before = read(text(row, "payload"));
      String account = text(before, "account_id");
      LocalDate date = LocalDate.parse(text(before, "publish_date"));
      List<Map<String, Object>> effective = source.effectiveMarketing(account, date);
      if (effective == null) throw new BusinessException(502, "有效营销投放查询未返回有效列表");
      List<Map<String, Object>> approved =
          effective.isEmpty() ? source.approvedMarketing(account) : Collections.emptyList();
      if (approved == null) throw new BusinessException(502, "过审营销内容查询未返回有效列表");
      List<Map<String, Object>> choices =
          new ArrayList<>(effective.isEmpty() ? approved : effective);
      if (effective.isEmpty())
        choices.sort(
            Comparator.<Map<String, Object>, Instant>comparing(SlotCompletionService::approvedAt)
                .thenComparing(c -> text(c, "content_id")));
      boolean changed =
          repo.transaction(
              () -> {
                Map<String, Object> current = repo.lockedItem(number(row, "id"));
                if (current == null
                    || !"awaiting_market".equals(current.get("content_status"))
                    || number(current, "version") != number(row, "version")) return false;
                Map<String, Object> item = read(text(current, "payload")), selected = null;
                for (Map<String, Object> content : choices) {
                  if (!account.equals(text(content, "account_id"))
                      || text(content, "content_id").isEmpty()
                      || text(content, "content_id").length() > 64
                      || text(content, "title").isEmpty())
                    throw new BusinessException(502, "营销内容账号或标识不一致");
                  if (effective.isEmpty() && approvedAt(content).isAfter(now)) continue;
                  if (!effective.isEmpty()
                      && !date.toString().equals(text(content, "publish_date")))
                    throw new BusinessException(502, "有效营销投放日期不一致");
                  if (slots.claimed("marketing_day", account + "|" + date) > 0) continue;
                  if (claim("marketing", text(content, "content_id"), number(current, "id"))) {
                    slots.claim("marketing_day", account + "|" + date, number(current, "id"));
                    selected = content;
                    break;
                  }
                }
                if (selected == null) {
                  item.putAll(
                      map("status", "待生产", "production_status", "planned", "slot_type", "regular"));
                  complete(current, item, "planned", "无可引用的营销内容，采用原普通选题", now);
                } else {
                  item.putAll(
                      map(
                          "topic_id",
                          "",
                          "topic_type",
                          "营销",
                          "content_id",
                          selected.get("content_id"),
                          "topic_title",
                          selected.get("title"),
                          "outline",
                          selected.get("body"),
                          "status",
                          "已完成",
                          "production_status",
                          "generated"));
                  complete(
                      current,
                      item,
                      "generated",
                      effective.isEmpty() ? "引用最早过审营销内容" : "引用当日已有效投放营销内容",
                      now);
                }
                return true;
              });
      if (changed) applied++;
    }
    return map(
        "applied",
        applied,
        "next_after_id",
        pending.isEmpty() ? after : number(pending.get(pending.size() - 1), "id"),
        "has_more",
        pending.size() == limit);
  }

  private void complete(
      Map<String, Object> current,
      Map<String, Object> item,
      String state,
      String reason,
      Instant now) {
    long version = number(current, "version") + 1;
    item.put("result_version", version);
    item.put("allow_replace", "planned".equals(state));
    if (slots.fill(number(current, "id"), (int) number(current, "version"), state, write(item))
        != 1) throw new BusinessException(409, "槽位已被其他任务更新");
    repo.saveAdjustment(
        number(current, "id"),
        write(
            map(
                "adjustment_source",
                "business_completion",
                "reason",
                reason,
                "new_topic_id",
                item.get("topic_id"),
                "new_topic_title",
                item.get("topic_title"),
                "content_id",
                item.get("content_id"),
                "result_version",
                version,
                "created_by",
                "host-scheduler",
                "created_at",
                now.toString())));
    progress.refreshBatch(number(current, "batch_id"));
  }

  private boolean claim(String kind, String key, long item) {
    if (key.length() > 160) throw new BusinessException(502, "内容资源标识超长");
    try {
      slots.claim(kind, key, item);
      return true;
    } catch (DuplicateKeyException used) {
      return false;
    }
  }

  private static void checkScan(int limit, long after) {
    if (limit < 1 || limit > 500 || after < 0) throw new BusinessException(422, "扫描范围无效");
  }

  private static Instant approvedAt(Map<String, Object> content) {
    try {
      return OffsetDateTime.parse(text(content, "approved_at")).toInstant();
    } catch (RuntimeException invalid) {
      throw new BusinessException(502, "营销审核通过时间无效");
    }
  }
}
