package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.*;

import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Transitional federation: read historical pages through a semantic port, merge Java facts, then
 * paginate. No copying of historical business data into either database.
 */
public class ManualQueryService {
  static final long JAVA_ID = 1000000000000L;
  private static final List<String> TYPES =
      Arrays.asList(
          "三公里好物种草", "产品权益种草", "三公里活动营销", "产品营销", "通用活动", "金融科普", "热点解读", "属地推荐", "一句话讨论", "财商教育",
          "客群兴趣内容", "人设故事");
  final ManualRepository repo;
  final ManualPlanningService service;
  final ManualPorts.Source source;
  final ManualPorts.Transition transition;
  final MarketingTaskService marketing;
  private final com.stratmatrix.planning.query.PlanningReadQueries reads;

  public ManualQueryService(
      ManualRepository repo,
      ManualPlanningService service,
      ManualPorts.Source source,
      ManualPorts.Transition transition) {
    this(repo, service, source, transition, null);
  }

  public ManualQueryService(
      ManualRepository repo,
      ManualPlanningService service,
      ManualPorts.Source source,
      ManualPorts.Transition transition,
      MarketingTaskService marketing) {
    this(repo, service, source, transition, marketing, null);
  }

  public ManualQueryService(
      ManualRepository repo,
      ManualPlanningService service,
      ManualPorts.Source source,
      ManualPorts.Transition transition,
      MarketingTaskService marketing,
      com.stratmatrix.planning.query.PlanningReadQueries reads) {
    this.repo = repo;
    this.service = service;
    this.source = source;
    this.transition = transition;
    this.marketing = marketing;
    this.reads = reads;
  }

  static String date(Map<String, Object> r, String key) {
    String s = text(r, key);
    return s.length() >= 10 ? s.substring(0, 10) : s;
  }

  static long timestamp(String value) {
    if (value == null || value.isEmpty()) return Long.MIN_VALUE;
    String iso = value.replace(' ', 'T');
    try {
      return OffsetDateTime.parse(iso).toInstant().toEpochMilli();
    } catch (java.time.format.DateTimeParseException noOffset) {
      try {
        return LocalDateTime.parse(iso)
            .atZone(ZoneId.of("Asia/Shanghai"))
            .toInstant()
            .toEpochMilli();
      } catch (java.time.format.DateTimeParseException invalid) {
        return Long.MIN_VALUE;
      }
    }
  }

  static String week(String date) {
    return LocalDate.parse(date)
        .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        .toString();
  }

  static boolean contains(Object v, String query) {
    return query.isEmpty()
        || (v != null
            && v.toString().toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT)));
  }

  static boolean range(String date, String start, String end) {
    return (start.isEmpty() || date.compareTo(start) >= 0)
        && (end.isEmpty() || date.compareTo(end) <= 0);
  }

  static void dates(String start, String end) {
    try {
      if (!start.isEmpty()) LocalDate.parse(start);
      if (!end.isEmpty()) LocalDate.parse(end);
      if (!start.isEmpty() && !end.isEmpty() && start.compareTo(end) > 0)
        throw new IllegalArgumentException();
    } catch (RuntimeException e) {
      throw new BusinessException(422, "请输入有效的起止日期");
    }
  }

  static int page(Map<String, Object> q) {
    int v = (int) number(q, "page");
    if (q.containsKey("page") && v < 1) throw new BusinessException(422, "页码无效");
    return v == 0 ? 1 : v;
  }

  static int size(Map<String, Object> q) {
    int v = (int) number(q, "page_size");
    if (q.containsKey("page_size") && (v < 1 || v > 200))
      throw new BusinessException(422, "每页数量无效");
    return v == 0 ? 20 : v;
  }

  static <T> List<T> slice(List<T> list, Map<String, Object> query) {
    long start = (long) (page(query) - 1) * size(query);
    return new ArrayList<>(
        list.subList(
            (int) Math.min(start, list.size()), (int) Math.min(start + size(query), list.size())));
  }

  static Map<String, Object> paged(List<?> list, Map<String, Object> query) {
    return map(
        "items",
        slice(list, query),
        "total",
        list.size(),
        "page",
        page(query),
        "page_size",
        size(query));
  }

  List<Map<String, Object>> history(String endpoint, Map<String, Object> query) {
    List<Map<String, Object>> all = new ArrayList<>();
    Map<String, Object> q = new LinkedHashMap<>(query);
    q.put("page_size", 200);
    for (int p = 1; ; p++) {
      q.put("page", p);
      Map<String, Object> result = transition.queryPage(endpoint, q);
      List<Map<String, Object>> part = rows(result.get("items"));
      all.addAll(part);
      if (all.size() >= number(result, "total")) return all;
      if (part.isEmpty() || p >= 500) throw new BusinessException(503, "历史查询范围过大，请缩小日期范围");
    }
  }

  public Map<String, Object> tasks(Map<String, Object> query) {
    if (reads != null) return reads.tasks(query);
    Map<String, Object> f = object(query.get("filters"));
    dates(text(f, "dateStart"), text(f, "dateEnd"));
    List<Map<String, Object>> out = history("manual-tasks", query);
    for (Map<String, Object> task : repo.tasks()) {
      Map<String, Object> row = service.taskView(task);
      String needle = text(f, "batch");
      if (!contains(row.get("task_name"), needle) && !contains(row.get("batch_code"), needle))
        continue;
      if (!contains(row.get("created_by"), text(f, "creator"))
          || !range(date(row, "publish_date"), text(f, "dateStart"), text(f, "dateEnd"))) continue;
      if (!text(f, "contentStatus").isEmpty()
          && !text(f, "contentStatus").equals(contentLabel(row))) continue;
      out.add(row);
    }
    if (marketing != null)
      for (Map<String, Object> row : marketing.all()) {
        String needle = text(f, "batch");
        if (!contains(row.get("task_name"), needle) && !contains(row.get("batch_code"), needle))
          continue;
        if (!contains(row.get("created_by"), text(f, "creator"))) continue;
        // Undated marketing demand does not meet a requested publish-date range.
        if (!text(f, "dateStart").isEmpty() || !text(f, "dateEnd").isEmpty()) continue;
        if (!text(f, "contentStatus").isEmpty()
            && !text(f, "contentStatus").equals(contentLabel(row))) continue;
        out.add(row);
      }
    out.sort(
        Comparator.<Map<String, Object>>comparingLong(r -> timestamp(text(r, "created_at")))
            .thenComparing(r -> text(r, "task_code"))
            .reversed());
    return paged(out, query);
  }

  static String contentLabel(Map<String, Object> task) {
    long completed = number(task, "content_completed_count");
    long failed = number(task, "content_failed_count");
    if (completed > 0 && failed > 0) return "部分失败";
    if (failed > 0) return "生成失败";
    String status = text(task, "content_status");
    if (status.contains("待分配")) return "待分配";
    if (status.contains("已完成")) return "已完成";
    if (status.contains("生成中") || status.contains("生产中")) return "生成中";
    return "待生成";
  }

  public Map<String, Object> batch(long id) {
    Map<String, Object> stored = repo.batchById(id);
    if (stored == null) throw new BusinessException(404, "批次不存在");
    Map<String, Object> batch = Json.read(String.valueOf(stored.get("payload")));
    batch.put("items", repo.itemsByBatch(id));
    return batch;
  }

  public List<Map<String, Object>> legacyRecords(Map<String, Object> query) {
    Map<String, Object> q = new LinkedHashMap<>(query);
    q.put("unit", "records");
    return history("plans", q);
  }

  public List<Map<String, Object>> exportRecords(Map<String, Object> query) {
    if (reads != null) return reads.records(query);
    Map<String, Object> q = new LinkedHashMap<>(query);
    Map<String, Object> f = object(q.get("filters"));
    dates(text(f, "start"), text(f, "end"));
    List<Map<String, Object>> local =
        "batch".equals(q.get("mode")) && number(q, "batch_id") >= JAVA_ID
            ? repo.itemsByBatch(number(q, "batch_id"))
            : repo.items();
    List<Map<String, Object>> frozen =
        new ArrayList<>(local.stream().filter(r -> matches(r, q)).collect(Collectors.toList()));
    if (!("batch".equals(q.get("mode")) && number(q, "batch_id") >= JAVA_ID)) {
      q.put("max_item_id", transition.resultWatermark());
      frozen.addAll(legacyRecords(q));
    }
    frozen.sort(
        Comparator.<Map<String, Object>, String>comparing(r -> date(r, "publish_date"))
            .thenComparingLong(r -> number(r, "id"))
            .reversed());
    return frozen;
  }

  boolean accountMatch(Map<String, Object> profile, Map<String, Object> f) {
    String key = text(f, "keyword");
    if (!contains(profile.get("account_id"), key) && !contains(profile.get("account_name"), key))
      return false;
    if (!contains(profile.get("um_no"), text(f, "umNo"))) return false;
    for (String[] pair :
        new String[][] {
          {"organization", "organization"},
          {"platform", "platform"},
          {"lifecycle", "lifecycle_stage"},
          {"accountType", "account_type"}
        })
      if (!text(f, pair[0]).isEmpty() && !text(f, pair[0]).equals(text(profile, pair[1])))
        return false;
    for (String k : Arrays.asList("followersMin", "followersMax"))
      if (!text(f, k).isEmpty()) {
        double n;
        try {
          n = Double.parseDouble(text(f, k));
        } catch (NumberFormatException e) {
          throw new BusinessException(422, "粉丝量范围无效");
        }
        if (profile.get("followers") == null
            || (k.equals("followersMin")
                ? number(profile, "followers") < n
                : number(profile, "followers") > n)) return false;
      }
    return true;
  }

  boolean matches(Map<String, Object> row, Map<String, Object> q) {
    Map<String, Object> f = object(q.get("filters"));
    String mode = text(q, "mode");
    if (mode.equals("batch") && number(q, "batch_id") != number(row, "batch_id")) return false;
    if (mode.equals("account") && !text(q, "account_id").equals(text(row, "account_id")))
      return false;
    if (mode.equals("cycle")
        && !range(date(row, "cycle_start"), text(q, "cycle_start"), text(q, "cycle_end")))
      return false;
    if (q.get("account_ids") instanceof List
        && !((List<?>) q.get("account_ids")).contains(row.get("account_id"))) return false;
    if (q.get("batch_ids") instanceof List
        && !((List<?>) q.get("batch_ids"))
            .stream().anyMatch(v -> v.toString().equals(text(row, "batch_id")))) return false;
    if (!range(date(row, "publish_date"), text(f, "start"), text(f, "end"))) return false;
    if (!contains(row.get("account_id"), text(f, "account"))
        && !contains(row.get("account_name"), text(f, "account"))) return false;
    if (Arrays.asList("manual", "auto").contains(f.get("planType"))
        && !Objects.equals(row.get("plan_type"), f.get("planType"))) return false;
    if (!text(f, "contentType").isEmpty()
        && !text(f, "contentType").equals("all")
        && !Objects.equals(row.get("content_type"), f.get("contentType"))) return false;
    return accountMatch(object(row.get("account_snapshot")), object(f.get("accountFilters")));
  }

  public Map<String, Object> plans(Map<String, Object> query) {
    if (reads != null) return reads.plans(query);
    Map<String, Object> f = object(query.get("filters"));
    dates(text(f, "start"), text(f, "end"));
    String mode = text(query, "mode");
    if (!Arrays.asList("account", "batch", "cycle", "all").contains(mode))
      throw new BusinessException(422, "请选择查询范围");
    if (mode.equals("account") && text(query, "account_id").isEmpty())
      throw new BusinessException(422, "请选择账号");
    if (mode.equals("batch") && number(query, "batch_id") < 1)
      throw new BusinessException(422, "请选择批次");
    if (mode.equals("cycle")) {
      if (text(query, "cycle_start").isEmpty() || text(query, "cycle_end").isEmpty())
        throw new BusinessException(422, "请选择周期");
      dates(text(query, "cycle_start"), text(query, "cycle_end"));
    }
    List<Map<String, Object>> records =
        mode.equals("batch") && number(query, "batch_id") >= JAVA_ID
            ? new ArrayList<>()
            : legacyRecords(query);
    List<Map<String, Object>> candidate =
        mode.equals("batch") && number(query, "batch_id") >= JAVA_ID
            ? repo.itemsByBatch(number(query, "batch_id"))
            : repo.items();
    List<Map<String, Object>> local =
        candidate.stream().filter(r -> matches(r, query)).collect(Collectors.toList());
    records.addAll(local);
    Map<String, Map<String, Object>> accounts = indexAccounts(records);
    Map<String, Object> summary =
        map(
            "accounts",
            records.stream().map(r -> r.get("account_id")).distinct().count(),
            "batches",
            records.stream().map(r -> r.get("batch_id")).distinct().count(),
            "topics",
            records.stream()
                .map(r -> text(r, "topic_id"))
                .filter(s -> !s.isEmpty())
                .distinct()
                .count());
    Set<String> types =
        records.stream()
            .map(r -> text(r, "content_type"))
            .filter(s -> !s.isEmpty())
            .collect(Collectors.toCollection(TreeSet::new));
    List<Map<String, Object>> distribution = new ArrayList<>();
    Set<String> names = new LinkedHashSet<>(TYPES);
    names.addAll(types);
    for (String name : names)
      distribution.add(
          map(
              "name",
              name,
              "count",
              records.stream()
                  .filter(r -> name.equals(text(r, "content_type")))
                  .map(r -> r.get("topic_id"))
                  .distinct()
                  .count(),
              "hint",
              "同一选题在同一内容类型下只计一次"));
    records.sort(
        Comparator.<Map<String, Object>, String>comparing(r -> date(r, "publish_date"))
            .thenComparingLong(r -> number(r, "id"))
            .reversed());
    boolean individual = "records".equals(query.get("unit"));
    Map<String, List<Map<String, Object>>> groups = new TreeMap<>();
    for (Map<String, Object> r : records) {
      String key =
          individual
              ? text(r, "id")
              : mode.equals("account") ? week(date(r, "publish_date")) : text(r, "account_id");
      groups.computeIfAbsent(key, k -> new ArrayList<>()).add(r);
    }
    List<String> keys = new ArrayList<>(groups.keySet());
    if (mode.equals("account")) Collections.reverse(keys);
    List<Map<String, Object>> selected =
        individual
            ? slice(records, query)
            : slice(keys, query).stream()
                .flatMap(k -> groups.get(k).stream())
                .collect(Collectors.toList());
    Map<String, Object> response =
        map(
            "items",
            selected,
            "total",
            groups.size(),
            "page",
            page(query),
            "page_size",
            size(query),
            "accounts",
            new ArrayList<>(accounts.values()),
            "summary",
            summary,
            "distribution",
            distribution,
            "content_types",
            new ArrayList<>(types));
    return response;
  }

  Map<String, Map<String, Object>> indexAccounts(List<Map<String, Object>> records) {
    Map<String, Map<String, Object>> out = new LinkedHashMap<>();
    for (Map<String, Object> row : records) {
      Map<String, Object> profile = object(row.get("account_snapshot"));
      if (!profile.isEmpty()) out.put(text(row, "account_id"), profile);
    }
    // Historical detail rows do not contain profiles; source endpoint is read-only.
    Set<String> missing =
        records.stream()
            .map(r -> text(r, "account_id"))
            .filter(id -> !out.containsKey(id))
            .collect(Collectors.toSet());
    if (!missing.isEmpty()) {
      List<String> ids = new ArrayList<>(missing);
      for (int i = 0; i < ids.size(); i += 500) {
        Map<String, Object> snapshot =
            source.sourceAccounts(ids.subList(i, Math.min(i + 500, ids.size())));
        for (Map<String, Object> a : rows(snapshot.get("accounts")))
          out.put(text(a, "account_id"), a);
      }
    }
    return out;
  }

  public Map<String, Object> accounts(Map<String, Object> query) {
    if (reads != null) return reads.accounts(query);
    List<Map<String, Object>> out = history("accounts", query);
    Map<String, Map<String, Object>> byId = ManualPlanningService.index(out, "account_id");
    Map<String, List<Map<String, Object>>> local =
        repo.items().stream().collect(Collectors.groupingBy(r -> text(r, "account_id")));
    for (Map.Entry<String, List<Map<String, Object>>> e : local.entrySet()) {
      Map<String, Object> profile = object(e.getValue().get(0).get("account_snapshot"));
      if (!accountMatch(profile, object(query.get("filters")))) continue;
      Map<String, Object> row = byId.get(e.getKey());
      if (row == null) {
        row =
            map(
                "account_id",
                e.getKey(),
                "account_name",
                profile.get("account_name"),
                "account_owner",
                profile.get("um_no"),
                "cycle_count",
                0,
                "slot_count",
                0,
                "latest_cycle_updated_at",
                "",
                "profile",
                profile);
        out.add(row);
      }
      row.put("slot_count", number(row, "slot_count") + e.getValue().size());
      Set<String> cycles =
          e.getValue().stream().map(r -> date(r, "cycle_start")).collect(Collectors.toSet());
      if (byId.containsKey(e.getKey()))
        for (Map<String, Object> old :
            legacyRecords(map("mode", "account", "account_id", e.getKey())))
          cycles.add(date(old, "cycle_start"));
      row.put("cycle_count", cycles.size());
      Map<String, Object> latest =
          e.getValue().stream()
              .max(Comparator.comparingLong(r -> timestamp(text(r, "batch_created_at"))))
              .get();
      if (timestamp(text(latest, "batch_created_at"))
          > timestamp(text(row, "latest_cycle_updated_at")))
        row.putAll(
            map(
                "latest_batch_id",
                latest.get("batch_id"),
                "latest_cycle_start",
                latest.get("cycle_start"),
                "latest_cycle_updated_at",
                latest.get("batch_created_at"),
                "latest_status",
                "已完成"));
    }
    out.sort(
        Comparator.<Map<String, Object>>comparingLong(
                r -> timestamp(text(r, "latest_cycle_updated_at")))
            .reversed()
            .thenComparing(r -> text(r, "account_id")));
    Map<String, Object> result = paged(out, query), facets = new LinkedHashMap<>();
    for (String[] pair :
        new String[][] {
          {"organizations", "organization"},
          {"platforms", "platform"},
          {"lifecycles", "lifecycle_stage"}
        })
      facets.put(
          pair[0],
          out.stream()
              .map(r -> text(object(r.get("profile")), pair[1]))
              .filter(s -> !s.isEmpty())
              .distinct()
              .sorted()
              .collect(Collectors.toList()));
    result.put("facets", facets);
    return result;
  }

  public List<Map<String, Object>> periodsAll(Map<String, Object> query) {
    Map<String, Object> filters = object(query.get("filters"));
    dates(text(filters, "startDate"), text(filters, "endDate"));
    List<Map<String, Object>> out = history("periods", query);
    Map<String, Map<String, Object>> byWeek = ManualPlanningService.index(out, "cycleStart");
    for (Map<String, Object> batch : repo.batches()) {
      String start = week(date(batch, "cycle_start")),
          end = LocalDate.parse(start).plusDays(6).toString();
      if (!text(filters, "startDate").isEmpty() && end.compareTo(text(filters, "startDate")) < 0)
        continue;
      if (!text(filters, "endDate").isEmpty() && start.compareTo(text(filters, "endDate")) > 0)
        continue;
      if (!contains(batch.get("batch_code"), text(filters, "batchQuery"))
          && !text(batch, "id").equals(text(filters, "batchQuery"))) continue;
      Map<String, Object> row = byWeek.get(start);
      if (row == null) {
        row =
            map(
                "cycleStart",
                start,
                "cycleEnd",
                end,
                "batches",
                new ArrayList<>(),
                "autoBatches",
                new ArrayList<>(),
                "manualBatches",
                new ArrayList<>(),
                "autoAccountCount",
                0,
                "manualAccountCount",
                0,
                "accountCount",
                0,
                "completedCount",
                0,
                "failedCount",
                0,
                "contentCompletedAccountCount",
                0,
                "updatedAt",
                batch.get("updated_at"));
        out.add(row);
        byWeek.put(start, row);
      }
      rows(row.get("batches")).add(batch);
      rows(row.get("manualBatches")).add(batch);
    }
    // Recompute distinct accounts for only the weeks touched by Java records.
    for (Map<String, Object> period : out) {
      if (rows(period.get("batches")).stream().noneMatch(b -> number(b, "id") >= JAVA_ID)) continue;
      Map<String, Object> q =
          map(
              "mode",
              "cycle",
              "cycle_start",
              period.get("cycleStart"),
              "cycle_end",
              period.get("cycleEnd"),
              "filters",
              map());
      List<Map<String, Object>> records = legacyRecords(q);
      records.addAll(repo.items().stream().filter(r -> matches(r, q)).collect(Collectors.toList()));
      long count = records.stream().map(r -> r.get("account_id")).distinct().count();
      period.put("accountCount", Math.max(number(period, "accountCount"), count));
      period.put(
          "manualAccountCount",
          records.stream()
              .filter(r -> "manual".equals(r.get("plan_type")))
              .map(r -> r.get("account_id"))
              .distinct()
              .count());
      period.put("completedCount", number(period, "accountCount") - number(period, "failedCount"));
      List<Map<String, Object>> batches = rows(period.get("batches"));
      batches.sort(
          Comparator.<Map<String, Object>>comparingLong(r -> timestamp(text(r, "created_at")))
              .reversed());
      period.put(
          "updatedAt",
          batches.stream()
              .map(
                  b ->
                      text(b, "updated_at").isEmpty()
                          ? text(b, "created_at")
                          : text(b, "updated_at"))
              .max(Comparator.comparingLong(ManualQueryService::timestamp))
              .orElse(""));
    }
    out.sort(
        Comparator.<Map<String, Object>, String>comparing(r -> text(r, "cycleStart")).reversed());
    return out;
  }

  public Map<String, Object> periods(Map<String, Object> query) {
    if (reads != null) return reads.periods(query);
    return paged(periodsAll(query), query);
  }

  public List<Map<String, Object>> context(Map<String, Object> query) {
    if (reads != null) return reads.context(query);
    String start = text(query, "cycle_start"), end = text(query, "cycle_end");
    if (number(query, "batch_id") >= JAVA_ID) {
      Map<String, Object> batch = batch(number(query, "batch_id"));
      start = week(date(batch, "cycle_start"));
      end = LocalDate.parse(start).plusDays(6).toString();
    } else if (number(query, "batch_id") > 0) {
      List<Map<String, Object>> old = transition.periodContext(query);
      if (!old.isEmpty()) {
        start = text(old.get(0), "cycleStart");
        end = text(old.get(0), "cycleEnd");
      }
    }
    return periodsAll(map("filters", map("startDate", start, "endDate", end)));
  }

  public boolean businessOnly() {
    return reads != null;
  }

  public boolean ownsBatch(long id) {
    return repo.batchById(id) != null;
  }

  public Map<String, Map<String, Object>> latestOperations(List<Long> ids) {
    return reads != null ? reads.latestOperations(ids) : Collections.emptyMap();
  }

  public List<Map<String, Object>> failures(Map<String, Object> query) {
    if (reads == null) throw new BusinessException(503, "业务库结果查询尚未启用");
    return reads.failures(query);
  }

  public Map<String, Object> archivedTask(String code) {
    if (reads == null) throw new BusinessException(404, "历史任务不存在");
    return reads.archivedTask(code);
  }
}
