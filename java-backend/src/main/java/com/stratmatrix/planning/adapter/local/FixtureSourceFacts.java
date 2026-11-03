package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.manual.BusinessException;
import com.stratmatrix.planning.source.SourceFacts;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.function.Predicate;

/** Sole outside source of raw bank facts. No Python call, database or generated fallback. */
public final class FixtureSourceFacts implements SourceFacts {
  private final Path path;

  public FixtureSourceFacts(Path path) {
    this.path = path.toAbsolutePath().normalize();
  }

  private List<Map<String, Object>> records(String collection, String identity) {
    try {
      Map<String, Object> document =
          read(new String(Files.readAllBytes(path), StandardCharsets.UTF_8));
      if ((collection.equals("accounts") || collection.equals("topics"))
          && !(document.get(collection) instanceof List))
        throw new BusinessException(503, "Java模拟资料缺少账号或选题集合");
      List<Map<String, Object>> result = new ArrayList<>();
      Set<String> ids = new HashSet<>();
      for (Map<String, Object> wrapper : rows(document.get(collection))) {
        Map<String, Object> row =
            object(wrapper.containsKey("data") ? wrapper.get("data") : wrapper);
        if (identity != null && (text(row, identity).isEmpty() || !ids.add(text(row, identity))))
          throw new BusinessException(503, "模拟资料存在缺失或重复标识");
        result.add(new LinkedHashMap<>(row));
      }
      if (collection.equals("marketing_contents"))
        result.sort(
            Comparator.<Map<String, Object>, Instant>comparing(r -> instant(r.get("approved_at")))
                .thenComparing(r -> text(r, "content_id")));
      else if (identity != null) result.sort(Comparator.comparing(r -> text(r, identity)));
      return result;
    } catch (IOException | IllegalArgumentException error) {
      throw new BusinessException(503, "Java模拟资料不可用，请检查夹具路径和文件格式");
    }
  }

  private static Object value(Map<String, Object> q, String name, String alias) {
    return q.containsKey(alias) ? q.get(alias) : q.get(name);
  }

  private static Instant instant(Object value) {
    try {
      String text = String.valueOf(value);
      try {
        return OffsetDateTime.parse(text).toInstant();
      } catch (java.time.format.DateTimeParseException ignored) {
        return LocalDateTime.parse(text).atZone(ZoneId.of("Asia/Shanghai")).toInstant();
      }
    } catch (RuntimeException error) {
      throw new BusinessException(422, "资料查询时间格式无效");
    }
  }

  private static boolean window(Map<String, Object> row, Map<String, Object> q) {
    Object from = value(q, "updated_from", "更新开始时间"), to = value(q, "updated_to", "更新结束时间");
    if (from != null && to != null && !instant(from).isBefore(instant(to)))
      throw new BusinessException(422, "更新开始时间必须早于结束时间");
    return (from == null || !instant(row.get("updated_at")).isBefore(instant(from)))
        && (to == null || instant(row.get("updated_at")).isBefore(instant(to)));
  }

  private static boolean ids(Map<String, Object> row, Map<String, Object> q, boolean account) {
    Object ids = value(q, account ? "account_ids" : "topic_ids", account ? "账号ID列表" : "选题ID列表");
    if (ids != null && (!(ids instanceof List) || ((List<?>) ids).size() > 500))
      throw new BusinessException(422, "资料ID列表无效或超出单批限制");
    return ids == null || ((List<?>) ids).contains(row.get(account ? "account_id" : "topic_id"));
  }

  private static int pageNumber(
      Map<String, Object> q, String key, String alias, int fallback, int max) {
    Object raw = value(q, key, alias);
    if (raw == null) return fallback;
    if (!(raw instanceof Number)
        || ((Number) raw).doubleValue() != ((Number) raw).intValue()
        || ((Number) raw).intValue() < 1
        || ((Number) raw).intValue() > max) throw new BusinessException(422, "资料分页参数无效");
    return ((Number) raw).intValue();
  }

  private Map<String, Object> page(
      String collection,
      String identity,
      Map<String, Object> q,
      Predicate<Map<String, Object>> filter) {
    int page = pageNumber(q, "page_no", "页码", 1, Integer.MAX_VALUE);
    int size = pageNumber(q, "page_size", "每页条数", 100, 500);
    List<Map<String, Object>> selected = new ArrayList<>();
    for (Map<String, Object> row : records(collection, identity))
      if (filter.test(row)) selected.add(row);
    int start = (int) Math.min(selected.size(), ((long) page - 1) * size);
    return map(
        "total",
        selected.size(),
        "page_no",
        page,
        "page_size",
        size,
        "items",
        selected.subList(start, Math.min(selected.size(), start + size)));
  }

  public Map<String, Object> accounts(Map<String, Object> q) {
    return page(
        "accounts",
        "account_id",
        q,
        r -> Boolean.TRUE.equals(r.get("eligible")) && ids(r, q, true) && window(r, q));
  }

  public Map<String, Object> topics(Map<String, Object> q) {
    Object source = value(q, "source", "选题来源"), type = value(q, "topic_type", "选题类型");
    Object available = value(q, "available_only", "仅可用选题"), at = value(q, "valid_at", "有效时点");
    return page(
        "topics",
        "topic_id",
        q,
        r ->
            ids(r, q, false)
                && window(r, q)
                && (source == null || source.equals(r.get("source")))
                && (type == null || type.equals(r.get("topic_type")))
                && (!Boolean.TRUE.equals(available) || Boolean.TRUE.equals(r.get("available")))
                && (at == null
                    || ((r.get("valid_from") == null
                            || !instant(r.get("valid_from")).isAfter(instant(at)))
                        && (r.get("valid_to") == null
                            || !instant(r.get("valid_to")).isBefore(instant(at))))));
  }

  public Map<String, Object> marketingContents(Map<String, Object> q) {
    Object account = value(q, "account_id", "账号ID");
    if (account == null || account.toString().trim().isEmpty())
      throw new BusinessException(422, "账号ID必填");
    return page("marketing_contents", "content_id", q, r -> account.equals(r.get("account_id")));
  }

  public Object effectiveMarketing(Map<String, Object> q) {
    Object account = value(q, "account_id", "账号ID"), date = value(q, "publish_date", "投放日期");
    List<Map<String, Object>> result = new ArrayList<>();
    for (Map<String, Object> row : records("placements", "placement_id"))
      if (Objects.equals(account, row.get("account_id"))
          && Objects.equals(date, row.get("publish_date"))) result.add(row);
    return result;
  }

  private Object statuses(String collection, Map<String, Object> q, String ids, String id) {
    if (!(q.get(ids) instanceof List)
        || ((List<?>) q.get(ids)).isEmpty()
        || ((List<?>) q.get(ids)).size() > 500) throw new BusinessException(422, "状态查询标识列表无效");
    List<Map<String, Object>> result = new ArrayList<>();
    for (Map<String, Object> row : records(collection, null))
      if (((List<?>) q.get(ids)).contains(row.get(id))) result.add(row);
    return result;
  }

  public Object productionStatus(Map<String, Object> q) {
    return statuses("production_results", q, "slot_ids", "slot_id");
  }

  public Object marketingStatus(Map<String, Object> q) {
    return statuses("marketing_results", q, "task_codes", "task_code");
  }

  public Object approvedDemandContents(Map<String, Object> q) {
    String task = text(q, "task_code");
    if (task.isEmpty()) throw new BusinessException(422, "营销需求编号必填");
    List<Map<String, Object>> result = new ArrayList<>();
    for (Map<String, Object> row : records("marketing_allocations", "content_id"))
      if (task.equals(row.get("task_code"))) result.add(row);
    return result;
  }
}
