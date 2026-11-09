package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.map;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import java.math.BigDecimal;
import java.util.*;

/** Shared bounded pagination. Explicit first-N vs complete reads; no silent partial completion. */
public final class SourcePageReader {
  public enum Capability {
    ACCOUNTS("account_id", "账号ID"),
    TOPICS("topic_id", "选题ID"),
    MARKETING_CONTENTS("content_id", "内容ID");
    final String identity, alias;

    Capability(String identity, String alias) {
      this.identity = identity;
      this.alias = alias;
    }
  }

  private final SourceFacts facts;
  private final int pageSize, maxPages;

  public SourcePageReader(SourceFacts facts) {
    this(facts, 500, 100);
  }

  public SourcePageReader(SourceFacts facts, int pageSize, int maxPages) {
    this.facts = Objects.requireNonNull(facts);
    if (pageSize < 1 || pageSize > 500 || maxPages < 1 || maxPages > 100)
      throw new IllegalArgumentException("资料分页预算无效");
    this.pageSize = pageSize;
    this.maxPages = maxPages;
  }

  public List<Map<String, Object>> first(
      Capability capability, Map<String, Object> query, int limit) {
    checkLimit(limit);
    return read(capability, query, limit, false, new HashSet<>(), new int[] {0});
  }

  public List<Map<String, Object>> all(Capability capability, Map<String, Object> query) {
    return read(capability, query, pageSize * maxPages, true, new HashSet<>(), new int[] {0});
  }

  public List<Map<String, Object>> byIds(Capability capability, List<String> ids, int limit) {
    checkLimit(limit);
    if (capability == Capability.MARKETING_CONTENTS)
      throw new IllegalArgumentException("营销内容按账号分页查询");
    if (ids == null) return first(capability, Collections.emptyMap(), limit);
    if (ids.size() > 50000) throw new BusinessException(422, "资料标识数量超过单次读取上限");
    List<String> unique = new ArrayList<>(new LinkedHashSet<>(ids));
    for (String id : unique)
      if (id == null || id.trim().isEmpty() || !id.equals(id.trim()) || id.length() > 64)
        throw new BusinessException(422, "资料标识格式无效");
    List<Map<String, Object>> result = new ArrayList<>();
    Set<String> seen = new HashSet<>();
    int[] requests = {0};
    for (int offset = 0; offset < unique.size() && result.size() < limit; offset += 500) {
      Map<String, Object> query =
          map(
              capability == Capability.ACCOUNTS ? "account_ids" : "topic_ids",
              new ArrayList<>(unique.subList(offset, Math.min(offset + 500, unique.size()))));
      result.addAll(read(capability, query, limit - result.size(), false, seen, requests));
    }
    return result;
  }

  private void checkLimit(int limit) {
    if (limit < 0 || limit > pageSize * maxPages) throw new IllegalArgumentException("资料读取数量超过预算");
  }

  private List<Map<String, Object>> read(
      Capability capability,
      Map<String, Object> query,
      int limit,
      boolean complete,
      Set<String> seen,
      int[] requests) {
    Objects.requireNonNull(capability);
    Objects.requireNonNull(query);
    List<Map<String, Object>> result = new ArrayList<>();
    if (limit == 0) return result;
    Long total = null;
    for (int page = 1; ; page++) {
      if (++requests[0] > maxPages) throw oversized();
      Map<String, Object> body = new LinkedHashMap<>(query);
      body.put("page_no", page);
      body.put("page_size", pageSize);
      Map<String, Object> response;
      switch (capability) {
        case ACCOUNTS:
          response = facts.accounts(body);
          break;
        case TOPICS:
          response = facts.topics(body);
          break;
        case MARKETING_CONTENTS:
          response = facts.marketingContents(body);
          break;
        default:
          throw new IllegalArgumentException("未知资料分页能力");
      }
      if (response == null) throw invalid("未返回分页对象");
      long count = integer(field(response, "total", "总数"));
      if (total != null && total != count) throw new BusinessException(409, "资料在读取期间发生变化，请重试");
      total = count;
      if (integer(field(response, "page_no", "页码")) != page
          || integer(field(response, "page_size", "每页条数")) != pageSize) throw invalid("页码或每页数量不匹配");
      Object raw = field(response, "items", "数据列表");
      if (!(raw instanceof List)) throw invalid("未返回资料列表");
      List<?> items = (List<?>) raw;
      long offset = ((long) page - 1) * pageSize;
      if (items.size() != Math.min(pageSize, Math.max(0, count - offset)))
        throw invalid("总数与当前页条数不一致");
      if (complete && count > result.size() + (long) (maxPages - requests[0] + 1) * pageSize)
        throw oversized();
      for (Object item : items) {
        if (!(item instanceof Map)) throw invalid("列表记录不是对象");
        @SuppressWarnings("unchecked")
        Map<String, Object> row = (Map<String, Object>) item;
        Object id = field(row, capability.identity, capability.alias);
        if (!(id instanceof String)
            || ((String) id).trim().isEmpty()
            || !id.equals(((String) id).trim())) throw invalid("资料记录缺少有效业务ID");
        String idsField = capability == Capability.ACCOUNTS ? "account_ids" : "topic_ids";
        Object scoped = query.get(idsField);
        if (scoped instanceof List && !((List<?>) scoped).contains(id))
          throw invalid("返回记录超出请求ID范围");
        if (capability == Capability.MARKETING_CONTENTS
            && query.get("account_id") != null
            && !query.get("account_id").equals(field(row, "account_id", "绑定账号ID")))
          throw invalid("营销内容账号不匹配");
        if (!seen.add((String) id)) throw invalid("重复业务ID或分页顺序不稳定");
        if (result.size() < limit) result.add(new LinkedHashMap<>(row));
      }
      if (offset + items.size() >= count || !complete && result.size() >= limit) return result;
    }
  }

  private static Object field(Map<String, Object> row, String name, String alias) {
    if (row.containsKey(name)
        && row.containsKey(alias)
        && !Objects.deepEquals(row.get(name), row.get(alias))) throw invalid("资料字段中英文值冲突");
    return row.containsKey(name) ? row.get(name) : row.get(alias);
  }

  private static long integer(Object value) {
    if (!(value instanceof Number)) throw invalid("分页元数据缺失或不是整数");
    try {
      long number = new BigDecimal(value.toString()).longValueExact();
      if (number < 0) throw invalid("分页元数据为负数");
      return number;
    } catch (ArithmeticException | NumberFormatException error) {
      throw invalid("分页元数据不是有效整数");
    }
  }

  private static BusinessException invalid(String message) {
    return new BusinessException(502, "资料分页不符合契约：" + message);
  }

  private static BusinessException oversized() {
    return new BusinessException(503, "资料查询超过读取预算，请缩小范围");
  }
}
