package com.stratmatrix.planning.query;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.manual.*;
import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import java.util.stream.Collectors;

/** Single-business-database result scopes, SQL pagination and full-scope statistics. */
public final class SqlPlanningReadQueries implements PlanningReadQueries {
  private static final List<String> TYPES =
      Arrays.asList(
          "三公里好物种草", "产品权益种草", "三公里活动营销", "产品营销", "通用活动", "金融科普", "热点解读", "属地推荐", "一句话讨论", "财商教育",
          "客群兴趣内容", "人设故事");
  private final PlanningQueryMapper sql;
  private final ManualRepository repo;
  private final ManualPlanningService manual;
  private final ManualPorts.AccountFacts accountFacts;

  public SqlPlanningReadQueries(
      PlanningQueryMapper sql, ManualRepository repo, ManualPlanningService manual) {
    this(sql, repo, manual, null);
  }

  public SqlPlanningReadQueries(
      PlanningQueryMapper sql,
      ManualRepository repo,
      ManualPlanningService manual,
      ManualPorts.AccountFacts accountFacts) {
    this.sql = sql;
    this.repo = repo;
    this.manual = manual;
    this.accountFacts = accountFacts;
  }

  private Map<String, Object> parameters(Map<String, Object> q) {
    Map<String, Object> p = new LinkedHashMap<>();
    Map<String, Object> f = object(q.get("filters")), a = object(f.get("accountFilters"));
    if (a.isEmpty()) a = f;
    int page = q.containsKey("page") ? (int) number(q, "page") : 1,
        size = q.containsKey("page_size") ? (int) number(q, "page_size") : 20;
    if (page < 1 || size < 1 || size > 200) throw new BusinessException(422, "分页范围无效");
    p.putAll(
        map(
            "page",
            page,
            "limit",
            size,
            "offset",
            (long) (page - 1) * size,
            "mode",
            text(q, "mode"),
            "unit",
            text(q, "unit"),
            "batchId",
            number(q, "batch_id"),
            "accountId",
            text(q, "account_id"),
            "cycleStart",
            text(q, "cycle_start"),
            "cycleEnd",
            text(q, "cycle_end"),
            "start",
            text(f, "start"),
            "end",
            text(f, "end"),
            "planType",
            text(f, "planType"),
            "contentType",
            text(f, "contentType"),
            "account",
            text(f, "account").isEmpty() ? text(a, "keyword") : text(f, "account"),
            "um",
            text(a, "umNo"),
            "organization",
            text(a, "organization"),
            "platform",
            text(a, "platform"),
            "lifecycle",
            text(a, "lifecycle"),
            "accountType",
            text(a, "accountType")));
    for (String key : Arrays.asList("followersMin", "followersMax"))
      if (!text(a, key).isEmpty()) {
        try {
          long value = Long.parseLong(text(a, key));
          if (value < 0) throw new NumberFormatException();
          p.put(key, value);
        } catch (NumberFormatException e) {
          throw new BusinessException(422, "粉丝量范围无效");
        }
      }
    if (p.containsKey("followersMin")
        && p.containsKey("followersMax")
        && (Long) p.get("followersMin") > (Long) p.get("followersMax"))
      throw new BusinessException(422, "粉丝量范围无效");
    dates(text(p, "start"), text(p, "end"));
    for (String key : Arrays.asList("account_ids", "batch_ids"))
      if (q.containsKey(key)) {
        Object ids = q.get(key);
        if (!(ids instanceof List) || ((List<?>) ids).isEmpty() || ((List<?>) ids).size() > 10000)
          throw new BusinessException(422, "查询标识列表无效");
        p.put(key.equals("account_ids") ? "accountIds" : "batchIds", ids);
      }
    return p;
  }

  public Map<String, Object> plans(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    validateScope(p);
    List<Map<String, Object>> groups = sql.groupKeys(p);
    List<Map<String, Object>> items = new ArrayList<>();
    if (!groups.isEmpty()) {
      Map<String, Object> selected = new LinkedHashMap<>(p);
      selected.put(
          "keys", groups.stream().map(r -> r.get("group_key")).collect(Collectors.toList()));
      selected.remove("limit");
      items = repo.materializeItems(sql.records(selected));
    }
    return planPage(p, items);
  }

  private static void validateScope(Map<String, Object> p) {
    String mode = text(p, "mode");
    if (!Arrays.asList("all", "account", "batch", "cycle").contains(mode))
      throw new BusinessException(422, "请选择查询范围");
    if (mode.equals("account") && text(p, "accountId").isEmpty()
        || mode.equals("batch") && number(p, "batchId") < 1)
      throw new BusinessException(422, "查询对象不能为空");
    if (mode.equals("cycle")) {
      dates(text(p, "cycleStart"), text(p, "cycleEnd"));
      if (text(p, "cycleStart").isEmpty() || text(p, "cycleEnd").isEmpty())
        throw new BusinessException(422, "请选择周期");
    }
  }

  private Map<String, Object> planPage(Map<String, Object> p, List<Map<String, Object>> items) {
    List<Map<String, Object>> counts = sql.distribution(p), distribution = new ArrayList<>();
    Set<String> types = new LinkedHashSet<>(TYPES);
    counts.forEach(c -> types.add(text(c, "name")));
    for (String type : types) {
      long count =
          counts.stream()
              .filter(c -> type.equals(c.get("name")))
              .mapToLong(c -> number(c, "amount"))
              .sum();
      distribution.add(map("name", type, "count", count, "hint", "同一选题在同一内容类型下只计一次"));
    }
    Map<String, Object> accounts =
        accountProfiles(
            items.stream().map(r -> text(r, "account_id")).distinct().collect(Collectors.toList()));
    return map(
        "items",
        items,
        "total",
        sql.groupCount(p),
        "page",
        p.get("page"),
        "page_size",
        p.get("limit"),
        "summary",
        sql.summary(p),
        "distribution",
        distribution,
        "content_types",
        counts.stream().map(r -> r.get("name")).collect(Collectors.toList()),
        "accounts",
        new ArrayList<>(accounts.values()));
  }

  private Map<String, Object> accountProfiles(List<String> ids) {
    Map<String, Object> out = new LinkedHashMap<>();
    if (ids.isEmpty()) return out;
    for (Map<String, Object> r : sql.accountSnapshots(map("ids", ids))) {
      Map<String, Object> item = read(text(r, "payload")),
          profile = AccountSnapshotView.from(object(item.get("account_snapshot")));
      if (profile.isEmpty())
        profile =
            map(
                "account_id",
                r.get("account_id"),
                "account_name",
                r.get("account_name"),
                "um_no",
                r.get("owner_um"));
      out.put(text(r, "account_id"), profile);
    }
    return out;
  }

  public Map<String, Object> accounts(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    p.put("mode", "all");
    List<Map<String, Object>> groups = sql.accountGroups(p);
    Map<String, Object> profiles =
        accountProfiles(
            groups.stream().map(r -> text(r, "account_id")).collect(Collectors.toList()));
    // Basic account-list information is current. Detail pages continue using
    // their frozen planning snapshots, without rewriting historical inputs.
    if (accountFacts != null && !groups.isEmpty()) {
      List<String> ids =
          groups.stream().map(r -> text(r, "account_id")).collect(Collectors.toList());
      for (Map<String, Object> current : rows(accountFacts.sourceAccounts(ids).get("accounts"))) {
        String id = text(current, "account_id");
        if (!profiles.containsKey(id)) continue;
        Map<String, Object> merged = new LinkedHashMap<>(object(profiles.get(id)));
        Map<String, Object> fresh = AccountSnapshotView.from(current);
        // SQL lifecycle filters use the latest planning snapshot. Keep those
        // derived fields aligned while refreshing the account's basic facts.
        for (Map.Entry<String, Object> field : fresh.entrySet()) {
          if (Arrays.asList("lifecycle_stage", "traffic_trend").contains(field.getKey())
              && merged.get(field.getKey()) != null) continue;
          merged.put(field.getKey(), field.getValue());
        }
        profiles.put(id, merged);
      }
    }
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> g : groups) {
      String id = text(g, "account_id");
      Map<String, Object> profile = object(profiles.get(id));
      out.add(
          map(
              "account_id",
              id,
              "account_name",
              profile.get("account_name"),
              "account_owner",
              profile.get("um_no"),
              "profile",
              profile,
              "slot_count",
              g.get("slot_count"),
              "cycle_count",
              g.get("cycle_count"),
              "latest_cycle_updated_at",
              Instant.ofEpochMilli(number(g, "latest_time")).toString(),
              "latest_status",
              "已完成"));
    }
    Map<String, Object> facets = new LinkedHashMap<>();
    List<Map<String, Object>> options = sql.facets(p);
    for (String[] pair :
        new String[][] {
          {"organizations", "organization"},
          {"platforms", "platform"},
          {"lifecycles", "lifecycle_stage"}
        })
      facets.put(
          pair[0],
          options.stream()
              .map(r -> text(r, pair[1]))
              .filter(s -> !s.isEmpty())
              .distinct()
              .sorted()
              .collect(Collectors.toList()));
    return map(
        "items",
        out,
        "total",
        sql.accountCount(p),
        "page",
        p.get("page"),
        "page_size",
        p.get("limit"),
        "facets",
        facets);
  }

  public Map<String, Object> periods(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    copyFilters(q, p, "startDate", "endDate", "batchQuery");
    dates(text(p, "startDate"), text(p, "endDate"));
    p.put("startWeek", text(p, "startDate").isEmpty() ? "" : week(text(p, "startDate")));
    List<Map<String, Object>> keys = sql.periodKeys(p), out = new ArrayList<>();
    if (!keys.isEmpty()) {
      p.put("weeks", keys.stream().map(k -> k.get("week_start")).collect(Collectors.toList()));
      List<Map<String, Object>> batches = sql.periodBatches(p);
      p.put("ids", batches.stream().map(b -> b.get("id")).collect(Collectors.toList()));
      Map<String, Map<String, Object>> stats = new HashMap<>();
      for (Map<String, Object> s : sql.periodAccounts(p)) stats.put(text(s, "week_start"), s);
      for (Map<String, Object> k : keys) {
        String start = text(k, "week_start");
        List<Map<String, Object>> all =
            batches.stream()
                .filter(b -> start.equals(b.get("week_start")))
                .map(b -> read(text(b, "payload")))
                .collect(Collectors.toList());
        List<Map<String, Object>>
            auto =
                all.stream()
                    .filter(b -> "auto".equals(b.get("plan_type")))
                    .collect(Collectors.toList()),
            manuals =
                all.stream()
                    .filter(b -> "manual".equals(b.get("plan_type")))
                    .collect(Collectors.toList());
        Map<String, Object> s = stats.getOrDefault(start, map());
        long failed = all.stream().mapToLong(b -> number(b, "failed_count")).sum();
        long accounts = number(s, "accounts");
        if (accounts == 0)
          accounts = all.stream().mapToLong(b -> number(b, "account_count")).max().orElse(0);
        String updated =
            all.stream().map(b -> text(b, "updated_at")).max(String::compareTo).orElse("");
        out.add(
            map(
                "cycleStart",
                start,
                "cycleEnd",
                LocalDate.parse(start).plusDays(6).toString(),
                "batches",
                all,
                "autoBatches",
                auto,
                "manualBatches",
                manuals,
                "autoAccountCount",
                number(s, "auto_accounts"),
                "manualAccountCount",
                number(s, "manual_accounts"),
                "accountCount",
                accounts,
                "completedCount",
                Math.max(0, accounts - failed),
                "failedCount",
                failed,
                "contentCompletedAccountCount",
                number(s, "completed_accounts"),
                "updatedAt",
                updated));
      }
    }
    return map(
        "items",
        out,
        "total",
        sql.periodCount(p),
        "page",
        p.get("page"),
        "page_size",
        p.get("limit"));
  }

  public List<Map<String, Object>> context(Map<String, Object> q) {
    String start = text(q, "cycle_start"), end = text(q, "cycle_end");
    if (number(q, "batch_id") > 0) {
      Map<String, Object> batch = repo.batchById(number(q, "batch_id"));
      if (batch == null) throw new BusinessException(404, "批次不存在");
      start = week(text(read(text(batch, "payload")), "cycle_start"));
      end = LocalDate.parse(start).plusDays(6).toString();
    }
    return rows(
        periods(map("filters", map("startDate", start, "endDate", end), "page_size", 200))
            .get("items"));
  }

  public Map<String, Object> tasks(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    copyFilters(q, p, "batch", "creator", "dateStart", "dateEnd", "contentStatus");
    dates(text(p, "dateStart"), text(p, "dateEnd"));
    String status = text(p, "contentStatus");
    p.put(
        "contentStatuses",
        status.contains("生成中")
            ? Arrays.asList("生成中", "生产中")
            : status.contains("失败")
                ? Arrays.asList("生成失败", "生产失败", "部分失败")
                : status.contains("待生成")
                    ? Arrays.asList("待生产", "待生成")
                    : Collections.singletonList(status));
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> r : sql.tasks(p)) {
      if ("manual".equals(r.get("kind"))) out.add(manual.taskView(repo.taskById(number(r, "id"))));
      else if ("marketing".equals(r.get("kind")))
        out.add(MarketingTaskService.summary(repo.marketingByCode(text(r, "batch_code"))));
      else out.add(read(text(r, "payload")));
    }
    return map(
        "items",
        out,
        "total",
        sql.taskCount(p),
        "page",
        p.get("page"),
        "page_size",
        p.get("limit"));
  }

  public List<Map<String, Object>> records(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    p.put("unit", "records");
    p.put("limit", 500);
    p.put("afterId", 0L);
    validateScope(p);
    List<Map<String, Object>> out = new ArrayList<>();
    while (true) {
      List<Map<String, Object>> page = sql.records(p);
      out.addAll(repo.materializeItems(page));
      if (page.size() < 500) break;
      p.put("afterId", number(page.get(page.size() - 1), "id"));
    }
    return out;
  }

  public List<Map<String, Object>> failures(Map<String, Object> q) {
    Map<String, Object> p = parameters(q);
    validateScope(p);
    return sql.failures(p).stream().map(r -> read(text(r, "payload"))).collect(Collectors.toList());
  }

  public Map<String, Object> archivedTask(String code) {
    Map<String, Object> row = sql.archivedTask(map("code", code));
    if (row == null) throw new BusinessException(404, "历史任务不存在");
    Map<String, Object> task = read(text(row, "payload")),
        detail = object(task.get("archive_detail"));
    return detail.isEmpty()
        ? map("task", task, "accounts", Collections.emptyList(), "topics", Collections.emptyList())
        : detail;
  }

  public Map<String, Map<String, Object>> latestOperations(List<Long> ids) {
    Map<String, Map<String, Object>> out = new HashMap<>();
    if (ids.isEmpty()) return out;
    for (Map<String, Object> row : sql.latestOperations(map("ids", ids))) {
      Map<String, Object> op = read(text(row, "payload"));
      out.put(String.valueOf(row.get("item_id")), op);
    }
    return out;
  }

  private static void copyFilters(
      Map<String, Object> query, Map<String, Object> parameters, String... keys) {
    Map<String, Object> fields = object(query.get("filters"));
    for (String key : keys) parameters.put(key, text(fields, key));
  }

  private static String week(String date) {
    return LocalDate.parse(date.substring(0, 10))
        .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        .toString();
  }

  private static void dates(String start, String end) {
    try {
      if (!start.isEmpty()) LocalDate.parse(start);
      if (!end.isEmpty()) LocalDate.parse(end);
      if (!start.isEmpty() && !end.isEmpty() && start.compareTo(end) > 0)
        throw new IllegalArgumentException();
    } catch (RuntimeException e) {
      throw new BusinessException(422, "起止日期无效");
    }
  }
}
