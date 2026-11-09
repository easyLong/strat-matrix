package com.pab.aitmp.aiis.godp.planning.server.controller;

import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ManualPreviewRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.MarketingTaskRequest;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualExportService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualItemService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualPlanningService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualQueryService;
import com.pab.aitmp.aiis.godp.planning.services.manual.MarketingTaskService;
import com.pab.aitmp.aiis.godp.planning.services.manual.TopicUsageService;
import com.pab.aitmp.aiis.godp.planning.services.manual.TopicValidity;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import java.time.LocalDate;
import java.util.*;
import javax.validation.Valid;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.PlanningQueryRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.ReplacementRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.TopicUsageRequest;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.CatalogQueryRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** Business page endpoints; queries and commands use one explicit POST contract. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
@PlanningPermission("results.view")
public class ManualPlanningController {
  private final ManualPlanningService service;
  private final ManualQueryService queries;
  private final ManualItemService items;
  private final ManualExportService exports;
  private final ManualPorts.Source source;
  private final ManualPorts.Transition transition;
  private final MarketingTaskService marketing;

  public ManualPlanningController(
      ManualPlanningService s,
      ManualQueryService q,
      ManualItemService i,
      ManualExportService e,
      ManualPorts.Source source,
      ManualPorts.Transition transition,
      MarketingTaskService marketing) {
    service = s;
    queries = q;
    items = i;
    exports = e;
    this.source = source;
    this.transition = transition;
    this.marketing = marketing;
  }

  @PostMapping("/manual-plans/previews")
  @ResponseStatus(HttpStatus.CREATED)
  @PlanningPermission("manual.create")
  public Object preview(@Valid @RequestBody ManualPreviewRequest input) {
    return service.preview(input);
  }

  @PostMapping("/manual-plans/previews/{code}/submit")
  @ResponseStatus(HttpStatus.ACCEPTED)
  @PlanningPermission("manual.create")
  public Object submit(@PathVariable String code) {
    if (!code.startsWith("JPREV-")) throw new BusinessException(409, "人工策划服务已升级，请重新提交当前选择");
    return service.submit(code);
  }

  @PostMapping("/manual-plans/account-availability/query")
  @PlanningPermission("manual.view")
  public Object availability(@Valid @RequestBody CatalogQueryRequest request) {
    String publish_date = request.publishDate;
    try {
      LocalDate.parse(publish_date);
    } catch (RuntimeException e) {
      throw new BusinessException(422, "投放日期无效");
    }
    return map(
        "publish_date", publish_date, "planned_account_ids", service.unavailable(publish_date));
  }

  @PostMapping("/accounts/query")
  @PlanningPermission({"manual.view","results.view"})
  public Object accountsCatalog(@Valid @RequestBody CatalogQueryRequest request) {
    int limit = request.limitOr(200);
    if (limit < 1 || limit > 1000) throw new BusinessException(422, "账号查询数量无效");
    return source.accountOptions(limit, request.includeDisabled);
  }

  @PostMapping("/topics/query")
  @PlanningPermission({"manual.view","results.view"})
  public Object topicsCatalog(@Valid @RequestBody CatalogQueryRequest request) {
    int limit = request.limitOr(200);
    if (limit < 1 || limit > 1000) throw new BusinessException(422, "选题查询数量无效");
    return source.topicCandidates(limit);
  }

  @PostMapping("/topics/{topicId}/detail/query")
  @PlanningPermission({"manual.view","results.view"})
  public Object topicDetail(
      @PathVariable String topicId,
      @Valid @RequestBody CatalogQueryRequest request) {
    String topicType = request.topicType;
    if (topicId == null
        || topicId.trim().isEmpty()
        || topicId.length() > 64
        || (topicType != null && !Arrays.asList("普通", "营销", "热点").contains(topicType)))
      throw new BusinessException(422, "选题ID或类型无效");
    return source.topicDetail(topicId, topicType);
  }

  @PostMapping("/query/manual-tasks")
  @PlanningPermission("manual.view")
  public Object tasks(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.tasks(q.values());
  }

  @PostMapping("/manual-plans/marketing-tasks")
  @ResponseStatus(HttpStatus.CREATED)
  @PlanningPermission("manual.create")
  public Object createMarketing(@Valid @RequestBody MarketingTaskRequest input) {
    return marketing.create(input);
  }

  @PostMapping("/manual-plans/marketing-tasks/query")
  @PlanningPermission("manual.view")
  public Object marketingTasks(@Valid @RequestBody CatalogQueryRequest request) {
    int limit = request.limitOr(20), offset = request.offset;
    if (limit < 1 || limit > 100 || offset < 0) throw new BusinessException(422, "分页参数无效");
    List<Map<String, Object>> all = new ArrayList<>(marketing.all());
    for (int previous = 0; ; previous += 100) {
      List<Map<String, Object>> old = transition.marketingTasks(100, previous);
      all.addAll(old);
      if (old.size() < 100) break;
      if (previous >= 49900) throw new BusinessException(503, "历史营销任务范围过大");
    }
    all.sort(
        Comparator.<Map<String, Object>>comparingLong(
                r -> ManualQueryService.timestamp(text(r, "created_at")))
            .thenComparing(r -> text(r, "task_code"))
            .reversed());
    return all.subList(
        Math.min(offset, all.size()), (int) Math.min((long) offset + limit, all.size()));
  }

  @PostMapping("/manual-plans/marketing-tasks/{code}/query")
  @PlanningPermission("manual.view")
  public Object marketingDetails(@PathVariable String code) {
    if (!code.matches("[A-Za-z0-9_-]{1,64}")) throw new BusinessException(422, "营销任务编号无效");
    return code.startsWith("JMAN-MKT-")
        ? marketing.detail(code)
        : queries.businessOnly()
            ? queries.archivedTask(code)
            : transition.marketingTaskDetails(code);
  }

  @PostMapping("/query/plans")
  public Object plans(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.plans(q.values());
  }

  @PostMapping("/query/accounts")
  public Object accounts(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.accounts(q.values());
  }

  @PostMapping("/query/periods")
  public Object periods(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.periods(q.values());
  }

  @PostMapping("/query/period-context")
  public Object context(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.context(q.values());
  }

  @PostMapping("/query/failures")
  public Object failures(@Valid @RequestBody PlanningQueryRequest q) {
    return queries.failures(q.values());
  }

  @PostMapping("/batches/query")
  public Object batches(@Valid @RequestBody CatalogQueryRequest request) {
    int limit = request.limitOr(200);
    String plan_type = request.planType;
    int size = Math.max(1, Math.min(limit, 1000));
    if (plan_type != null && !Arrays.asList("auto", "manual").contains(plan_type))
      throw new BusinessException(422, "策划方式无效");
    return queries.batches(size, plan_type);
  }

  @PostMapping("/manual-plans/tasks/query")
  @PlanningPermission("manual.view")
  public Object taskList(@Valid @RequestBody CatalogQueryRequest request) {
    int limit = request.limitOr(20), offset = request.offset;
    int count = Math.max(1, Math.min(limit, 100));
    if (offset < 0) throw new BusinessException(422, "分页起点无效");
    List<Map<String, Object>> all = new ArrayList<>();
    for (int p = 1; ; p++) {
      Map<String, Object> result = queries.tasks(map("page", p, "page_size", 200));
      all.addAll(rows(result.get("items")));
      if (all.size() >= number(result, "total")) break;
    }
    all.removeIf(r -> "marketing".equals(r.get("content_mode")));
    return all.subList(
        Math.min(offset, all.size()), (int) Math.min((long) offset + count, all.size()));
  }

  @PostMapping("/batches/{id}/query")
  public Object batch(@PathVariable long id) {
    return queries.ownsBatch(id) ? queries.batch(id) : transition.batch(id);
  }

  @PostMapping("/items/{id}/replace-topic")
  @PlanningPermission("results.replace")
  public Object replace(@PathVariable long id, @Valid @RequestBody ReplacementRequest r) {
    return queries.ownsItem(id)
        ? items.replace(id, r.values())
        : transition.replaceTopic(id, r.values());
  }

  @PostMapping("/items/{id}/adjustments/query")
  public Object adjustments(@PathVariable long id) {
    return queries.ownsItem(id) ? items.adjustments(id) : transition.adjustments(id);
  }

  @PostMapping("/items/{id}/replacement-candidates/query")
  @PlanningPermission("results.replace")
  public Object candidates(@PathVariable long id) {
    if (!queries.ownsItem(id)) return transition.replacementCandidates(id);
    Map<String, Object> item = queries.item(id);
    if (item == null) throw new BusinessException(404, "策划明细不存在");
    if (!Boolean.TRUE.equals(item.get("allow_replace")))
      throw new BusinessException(409, "仅待生产状态可以替换选题");
    List<Map<String, Object>> topics = new ArrayList<>(source.topicCandidates(1000));
    topics.removeIf(
        t ->
            Boolean.TRUE.equals(t.get("is_marketing"))
                || !TopicValidity.includes(t, LocalDate.parse(text(item, "publish_date")))
                || Objects.equals(t.get("topic_id"), item.get("topic_id")));
    return topics;
  }

  @PostMapping("/query/export")
  @PlanningPermission("results.export")
  public ResponseEntity<byte[]> export(@Valid @RequestBody PlanningQueryRequest request) {
    Map<String,Object> input=request.values();
    boolean excel = "xlsx".equals(text(input, "format"));
    byte[] data = exports.export(input);
    return ResponseEntity.ok()
        .header("Content-Disposition", "attachment; filename=planning." + (excel ? "xlsx" : "csv"))
        .contentType(
            excel
                ? MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                : MediaType.parseMediaType("text/csv;charset=UTF-8"))
        .body(data);
  }

  @PostMapping({"/query/topic-usage", "/integrations/bank/op02/topic-usage/query"})
  public Object topicUsage(@Valid @RequestBody TopicUsageRequest input) {
    return queries.topicUsage(input.values());
  }

}
