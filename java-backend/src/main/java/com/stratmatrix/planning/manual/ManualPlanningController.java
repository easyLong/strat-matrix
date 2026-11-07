package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.*;

import java.time.LocalDate;
import java.util.*;
import javax.validation.Valid;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** Explicit migrated endpoints take precedence over the transitional wildcard. */
@RestController
@RequestMapping("${planning.api-prefix:/api/plan}")
@ConditionalOnProperty(name = "planning.manual.enabled", havingValue = "true")
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
  public Object preview(@Valid @RequestBody ManualPreviewRequest input) {
    return service.preview(input);
  }

  @PostMapping("/manual-plans/previews/{code}/submit")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public Object submit(@PathVariable String code) {
    if (!code.startsWith("JPREV-")) throw new BusinessException(409, "人工策划服务已升级，请重新提交当前选择");
    return service.submit(code);
  }

  @GetMapping("/manual-plans/account-availability")
  public Object availability(@RequestParam String publish_date) {
    try {
      LocalDate.parse(publish_date);
    } catch (RuntimeException e) {
      throw new BusinessException(422, "投放日期无效");
    }
    return map(
        "publish_date", publish_date, "planned_account_ids", service.unavailable(publish_date));
  }

  @GetMapping("/accounts")
  public Object accountsCatalog(
      @RequestParam(defaultValue = "200") int limit,
      @RequestParam(defaultValue = "false") boolean include_disabled) {
    if (limit < 1 || limit > 1000) throw new BusinessException(422, "账号查询数量无效");
    return source.accountOptions(limit, include_disabled);
  }

  @GetMapping("/topics")
  public Object topicsCatalog(@RequestParam(defaultValue = "200") int limit) {
    if (limit < 1 || limit > 1000) throw new BusinessException(422, "选题查询数量无效");
    return source.topicCandidates(limit);
  }

  @GetMapping("/topics/{topicId}/detail")
  public Object topicDetail(
      @PathVariable String topicId,
      @RequestParam(name = "topic_type", required = false) String topicType) {
    if (topicId == null
        || topicId.trim().isEmpty()
        || topicId.length() > 64
        || (topicType != null && !Arrays.asList("普通", "营销", "热点").contains(topicType)))
      throw new BusinessException(422, "选题ID或类型无效");
    return source.topicDetail(topicId, topicType);
  }

  @PostMapping("/query/manual-tasks")
  public Object tasks(@RequestBody Map<String, Object> q) {
    return queries.tasks(q);
  }

  @PostMapping("/manual-plans/marketing-tasks")
  @ResponseStatus(HttpStatus.CREATED)
  public Object createMarketing(@Valid @RequestBody MarketingTaskRequest input) {
    return marketing.create(input);
  }

  @GetMapping("/manual-plans/marketing-tasks")
  public Object marketingTasks(
      @RequestParam(defaultValue = "20") int limit, @RequestParam(defaultValue = "0") int offset) {
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

  @GetMapping("/manual-plans/marketing-tasks/{code}")
  public Object marketingDetails(@PathVariable String code) {
    if (!code.matches("[A-Za-z0-9_-]{1,64}")) throw new BusinessException(422, "营销任务编号无效");
    return code.startsWith("JMAN-MKT-")
        ? marketing.detail(code)
        : queries.businessOnly()
            ? queries.archivedTask(code)
            : transition.marketingTaskDetails(code);
  }

  @PostMapping("/query/plans")
  public Object plans(@RequestBody Map<String, Object> q) {
    return queries.plans(q);
  }

  @PostMapping("/query/accounts")
  public Object accounts(@RequestBody Map<String, Object> q) {
    return queries.accounts(q);
  }

  @PostMapping("/query/periods")
  public Object periods(@RequestBody Map<String, Object> q) {
    return queries.periods(q);
  }

  @PostMapping("/query/period-context")
  public Object context(@RequestBody Map<String, Object> q) {
    return queries.context(q);
  }

  @PostMapping("/query/failures")
  public Object failures(@RequestBody Map<String, Object> q) {
    return queries.failures(q);
  }

  @GetMapping("/batches")
  public Object batches(
      @RequestParam(defaultValue = "200") int limit,
      @RequestParam(required = false) String plan_type) {
    int size = Math.max(1, Math.min(limit, 1000));
    if (plan_type != null && !Arrays.asList("auto", "manual").contains(plan_type))
      throw new BusinessException(422, "策划方式无效");
    List<Map<String, Object>> list = new ArrayList<>(transition.batches(size, plan_type));
    queries.repo.batches().stream()
        .filter(b -> plan_type == null || plan_type.equals(b.get("plan_type")))
        .forEach(list::add);
    list.sort(
        Comparator.<Map<String, Object>>comparingLong(
                r -> ManualQueryService.timestamp(text(r, "created_at")))
            .reversed());
    return list.subList(0, Math.min(size, list.size()));
  }

  @GetMapping("/manual-plans/tasks")
  public Object taskList(
      @RequestParam(defaultValue = "20") int limit, @RequestParam(defaultValue = "0") int offset) {
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

  @GetMapping("/batches/{id}")
  public Object batch(@PathVariable long id) {
    return queries.ownsBatch(id) ? queries.batch(id) : transition.batch(id);
  }

  @PostMapping("/batches/manual")
  public Object oldCreate() {
    throw new BusinessException(410, "请通过人工策划预览和提交创建任务");
  }

  @PostMapping("/items/{id}/replace-topic")
  public Object replace(@PathVariable long id, @RequestBody Map<String, Object> r) {
    return queries.repo.itemById(id) != null
        ? items.replace(id, r)
        : transition.replaceTopic(id, r);
  }

  @GetMapping("/items/{id}/adjustments")
  public Object adjustments(@PathVariable long id) {
    return queries.repo.itemById(id) != null ? items.adjustments(id) : transition.adjustments(id);
  }

  @GetMapping("/items/{id}/replacement-candidates")
  public Object candidates(@PathVariable long id) {
    if (queries.repo.itemById(id) == null) return transition.replacementCandidates(id);
    Map<String, Object> item = queries.repo.itemById(id);
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
  public ResponseEntity<byte[]> export(@RequestBody Map<String, Object> input) {
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
  public Object topicUsage(@RequestBody Map<String, Object> input) {
    return new TopicUsageService(queries.repo).query(input);
  }
}
