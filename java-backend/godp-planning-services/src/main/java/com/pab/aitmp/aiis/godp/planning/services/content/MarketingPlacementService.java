package com.pab.aitmp.aiis.godp.planning.services.content;

import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;

/**
 * Manual marketing receives content-owned account allocation; Java chooses the actual publish date.
 */
public final class MarketingPlacementService {
  private final ManualRepository repo;
  private final PlanningContentPort source;
  private final SlotCompletionMapper slots;
  private final BusinessPlanningConfigService rules;

  public MarketingPlacementService(
      ManualRepository repo,
      PlanningContentPort source,
      SlotCompletionMapper slots,
      BusinessPlanningConfigService rules) {
    this.repo = repo;
    this.source = source;
    this.slots = slots;
    this.rules = rules;
  }

  public Map<String, Object> reconcile(Instant now, int limit) {
    BusinessPlanningConfig config = rules.current().config;
    if (config.marketing_max == 0) return map("applied", 0, "status", "marketing_disabled");
    int applied = 0;
    for (Map<String, Object> task : repo.unlinkedMarketingTasks(limit)) {
      List<Map<String, Object>> contents = source.approvedDemandContents(text(task, "task_code"));
      if (contents == null) throw new BusinessException(502, "营销任务内容查询未返回列表");
      contents = new ArrayList<>(contents);
      contents.sort(
          Comparator.<Map<String, Object>, Instant>comparing(
                  c -> OffsetDateTime.parse(text(c, "approved_at")).toInstant())
              .thenComparing(c -> text(c, "content_id")));
      for (Map<String, Object> content : contents) {
        if (slots.claimed("marketing", text(content, "content_id")) > 0) continue;
        Map<String, Object> latest = repo.marketingByCode(text(task, "task_code"));
        if (number(latest, "linked_count") >= number(latest, "allocation_count")) break;
        Map<String, Object> account = object(content.get("account_snapshot"));
        String accountId = text(content, "account_id");
        if (text(content, "content_id").isEmpty()
            || !accountId.equals(text(account, "account_id"))
            || !"认证".equals(account.get("account_type"))
            || text(content, "title").isEmpty())
          throw new BusinessException(502, "营销分配内容缺少有效账号或过审内容资料");
        LocalDate first = now.atZone(ZoneId.of("Asia/Shanghai")).toLocalDate();
        Instant approved = OffsetDateTime.parse(text(content, "approved_at")).toInstant();
        if (approved.isAfter(now)) continue;
        boolean linked = false;
        for (int offset = 0; offset < 56 && !linked; offset++) {
          LocalDate date = first.plusDays(offset);
          if (!config.planning_days.contains(date.getDayOfWeek().getValue())) continue;
          List<Map<String, Object>> effective = source.effectiveMarketing(accountId, date);
          if (effective == null) throw new BusinessException(502, "有效营销投放查询不可用");
          if (!effective.isEmpty()) continue;
          LocalDate monday = date.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
          if (slots.contentLinks(accountId, monday.toString(), monday.plusDays(6).toString())
              >= config.marketing_max) continue;
          try {
            linked =
                repo.transaction(
                    () -> {
                      Map<String, Object> current =
                          repo.lockedMarketingTask(text(task, "task_code"));
                      if (number(current, "linked_count") >= number(current, "allocation_count"))
                        return true;
                      long batchId = number(current, "id") + 3000000000000L;
                      if (repo.batchById(batchId) == null)
                        repo.saveBatch(
                            batchId,
                            write(
                                map(
                                    "id",
                                    batchId,
                                    "batch_code",
                                    current.get("task_code"),
                                    "task_name",
                                    current.get("task_name"),
                                    "plan_type",
                                    "manual",
                                    "status",
                                    "已完成",
                                    "planning_status",
                                    "已完成",
                                    "cycle_start",
                                    date.toString(),
                                    "cycle_end",
                                    date.toString(),
                                    "created_at",
                                    now.toString(),
                                    "updated_at",
                                    now.toString())),
                            now.toEpochMilli());
                      String contentId = text(content, "content_id");
                      Map<String, Object> item =
                          map(
                              "batch_id",
                              batchId,
                              "batch_code",
                              current.get("task_code"),
                              "task_name",
                              current.get("task_name"),
                              "plan_type",
                              "manual",
                              "content_mode",
                              "marketing",
                              "account_id",
                              accountId,
                              "account_name",
                              account.get("account_name"),
                              "account_snapshot",
                              account,
                              "publish_date",
                              date.toString(),
                              "cycle_start",
                              monday.toString(),
                              "cycle_end",
                              monday.plusDays(6).toString(),
                              "slot_id",
                              "MKT-" + contentId,
                              "slot_type",
                              "marketing_priority",
                              "topic_id",
                              current.get("topic_id"),
                              "topic_type",
                              "营销",
                              "content_id",
                              contentId,
                              "topic_title",
                              content.get("title"),
                              "outline",
                              content.get("body"),
                              "content_type",
                              content.get("content_type"),
                              "status",
                              "已完成",
                              "production_status",
                              "generated",
                              "allow_replace",
                              false,
                              "result_version",
                              1,
                              "batch_created_at",
                              now.toString());
                      long itemId =
                          repo.saveItem(
                              batchId,
                              text(item, "slot_id"),
                              accountId,
                              date.toString(),
                              write(item),
                              "generated");
                      slots.claim("marketing", contentId, itemId);
                      slots.claim("marketing_day", accountId + "|" + date, itemId);
                      long count =
                          slots.contentLinks(
                              accountId, monday.toString(), monday.plusDays(6).toString());
                      boolean budget = false;
                      for (int i = (int) count - 1; i < config.marketing_max; i++) {
                        try {
                          slots.claim("marketing_week", accountId + "|" + monday + "|" + i, itemId);
                          budget = true;
                          break;
                        } catch (DuplicateKeyException full) {
                          /* try the remaining weekly allowance */
                        }
                      }
                      if (!budget) throw new DateUnavailable();
                      repo.attachMarketingBatch(
                          number(current, "id"),
                          batchId,
                          (int) number(current, "linked_count") + 1);
                      List<Map<String, Object>> all = repo.itemsByBatch(batchId);
                      Map<String, Object> batch = read(text(repo.lockedBatch(batchId), "payload"));
                      long accounts = all.stream().map(r -> r.get("account_id")).distinct().count();
                      if (number(current, "linked_count") + 1
                          >= number(current, "allocation_count"))
                        repo.updateMarketingProgress(
                            number(current, "id"),
                            "已完成",
                            (int) accounts,
                            (int) number(current, "allocation_count"),
                            0,
                            now.toEpochMilli());
                      batch.putAll(
                          map(
                              "account_count",
                              accounts,
                              "completed_count",
                              accounts,
                              "failed_count",
                              0,
                              "topic_count",
                              1,
                              "content_count",
                              all.size(),
                              "content_status",
                              "已完成",
                              "content_total_count",
                              all.size(),
                              "content_completed_count",
                              all.size(),
                              "content_completed_account_count",
                              accounts,
                              "cycle_start",
                              all.stream()
                                  .map(r -> text(r, "publish_date"))
                                  .min(String::compareTo)
                                  .get(),
                              "cycle_end",
                              all.stream()
                                  .map(r -> text(r, "publish_date"))
                                  .max(String::compareTo)
                                  .get(),
                              "updated_at",
                              now.toString()));
                      repo.updateBatch(batchId, write(batch));
                      repo.saveAdjustment(
                          itemId,
                          write(
                              map(
                                  "adjustment_source",
                                  "marketing_placement",
                                  "reason",
                                  "引用过审营销内容并确定投放日期",
                                  "content_id",
                                  contentId,
                                  "publish_date",
                                  date.toString(),
                                  "created_by",
                                  "host-scheduler",
                                  "created_at",
                                  now.toString())));
                      return true;
                    });
          } catch (DuplicateKeyException used) {
            if (slots.claimed("marketing", text(content, "content_id")) > 0) break;
          } catch (DateUnavailable full) {
            /* inspect the next configured date */
          }
        }
        if (linked) applied++;
      }
    }
    return map("applied", applied);
  }

  private static final class DateUnavailable extends RuntimeException {}
}
