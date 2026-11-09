package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;

import static com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json.map;
import static com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceValues.*;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import java.util.*;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * Bank entry: validate request -> read bank facts -> map/validate response. No source-table writes.
 */
public final class BankSourceFacts implements SourceFacts {
  private final BankSourceQueries queries;
  private final BankSourceMapping mapping;

  public BankSourceFacts(BankSourceQueries queries) {
    this(queries, new BankSourceMapping());
  }

  public BankSourceFacts(BankSourceQueries queries, BankSourceMapping mapping) {
    this.queries = Objects.requireNonNull(queries);
    this.mapping = Objects.requireNonNull(mapping);
  }

  public void verifyReady() { queries.verifyReady(); }

  public Map<String, Object> accounts(Map<String, Object> input) {
    BankSourceContracts.Accounts q = new BankSourceContracts.Accounts(input);
    if (q.accountIds != null && q.accountIds.isEmpty()) return empty(q);
    return page(
        q,
        read(() -> queries.accounts(q)),
        mapping::account,
        "account_id",
        r -> {
          if (!Boolean.TRUE.equals(r.get("eligible"))) throw invalid(502, "不可参与策划账号不应计入分页");
          scoped(r, "account_id", q.accountIds);
          window(r, q);
        });
  }

  public Map<String, Object> topics(Map<String, Object> input) {
    BankSourceContracts.Topics q = new BankSourceContracts.Topics(input);
    if (q.topicIds != null && q.topicIds.isEmpty()) return empty(q);
    return page(
        q,
        read(() -> queries.topics(q)),
        mapping::topic,
        "topic_id",
        r -> {
          scoped(r, "topic_id", q.topicIds);
          window(r, q);
          if (q.source != null && !q.source.equals(r.get("source"))
              || q.topicType != null && !q.topicType.equals(r.get("topic_type"))
              || q.availableOnly && !Boolean.TRUE.equals(r.get("available")))
            throw invalid(502, "选题返回超出筛选范围");
          if (q.validAt != null
              && (r.get("valid_from") != null
                      && BankSourceMapping.instant(r, "valid_from").isAfter(q.validAt)
                  || r.get("valid_to") != null
                      && BankSourceMapping.instant(r, "valid_to").isBefore(q.validAt)))
            throw invalid(502, "选题不在有效时点范围");
        });
  }

  public Map<String, Object> marketingContents(Map<String, Object> input) {
    BankSourceContracts.Marketing q = new BankSourceContracts.Marketing(input);
    return page(
        q,
        read(() -> queries.marketingContents(q)),
        mapping::marketing,
        "content_id",
        r -> scoped(r, "account_id", Collections.singletonList(q.accountId)));
  }

  public Object effectiveMarketing(Map<String, Object> input) {
    BankSourceContracts.Placement q = new BankSourceContracts.Placement(input);
    return records(
        read(() -> queries.effectiveMarketing(q)),
        mapping::placement,
        r -> String.valueOf(r.get("placement_id")),
        r -> {
          scoped(r, "account_id", Collections.singletonList(q.accountId));
          if (!q.publishDate.toString().equals(r.get("publish_date")))
            throw invalid(502, "营销投放日期不匹配");
        });
  }

  public Object productionStatus(Map<String, Object> input) {
    BankSourceContracts.Production q = new BankSourceContracts.Production(input);
    return records(
        read(() -> queries.productionStatus(q)),
        mapping::production,
        r -> r.get("slot_id") + "|" + r.get("version"),
        r -> scoped(r, "slot_id", q.slotIds));
  }

  public Object marketingStatus(Map<String, Object> input) {
    BankSourceContracts.MarketingStatus q = new BankSourceContracts.MarketingStatus(input);
    return records(
        read(() -> queries.marketingStatus(q)),
        mapping::marketingStatus,
        r -> String.valueOf(r.get("task_code")),
        r -> scoped(r, "task_code", q.taskCodes));
  }

  public Object approvedDemandContents(Map<String, Object> input) {
    BankSourceContracts.ApprovedDemand q = new BankSourceContracts.ApprovedDemand(input);
    List<Map<String, Object>> out =
        records(
            read(() -> queries.approvedDemandContents(q)),
            mapping::approved,
            r -> String.valueOf(r.get("content_id")),
            r -> scoped(r, "task_code", Collections.singletonList(q.taskCode)));
    out.sort(
        Comparator.<Map<String, Object>, java.time.Instant>comparing(
                r -> BankSourceMapping.instant(r, "approved_at"))
            .thenComparing(r -> String.valueOf(r.get("content_id"))));
    return out;
  }

  private static <T> T read(Supplier<T> operation) {
    try {
      return operation.get();
    } catch (BusinessException failure) {
      throw failure;
    } catch (RuntimeException failure) {
      throw new BusinessException(503, "行内资料查询暂不可用，请检查资料接入配置");
    }
  }

  private static void scoped(Map<String, Object> row, String key, List<String> ids) {
    if (ids != null && !ids.contains(row.get(key))) throw invalid(502, "返回记录超出请求的" + key + "范围");
  }

  private static void window(Map<String, Object> row, BankSourceContracts.UpdatedPage q) {
    java.time.Instant updated = BankSourceMapping.instant(row, "updated_at");
    if (q.updatedFrom != null && updated.isBefore(q.updatedFrom)
        || q.updatedTo != null && !updated.isBefore(q.updatedTo))
      throw invalid(502, "返回记录超出更新时间范围");
  }

  private static Map<String, Object> empty(BankSourceContracts.PageQuery q) {
    return map(
        "items",
        Collections.emptyList(),
        "total",
        0L,
        "page_no",
        q.pageNo,
        "page_size",
        q.pageSize);
  }

  private static Map<String, Object> page(
      BankSourceContracts.PageQuery q,
      BankSourceContracts.PageRows page,
      Function<Map<String, Object>, Map<String, Object>> mapping,
      String identity,
      Consumer<Map<String, Object>> validate) {
    if (page == null) throw invalid(502, "查询没有返回分页对象");
    long expected = Math.min(q.pageSize, Math.max(0, page.total - q.offset));
    if (page.items.size() != expected) throw invalid(502, "总数与本页条数不一致");
    List<Map<String, Object>> rows =
        records(page.items, mapping, r -> String.valueOf(r.get(identity)), validate);
    return map("items", rows, "total", page.total, "page_no", q.pageNo, "page_size", q.pageSize);
  }

  private static List<Map<String, Object>> records(
      List<Map<String, Object>> input,
      Function<Map<String, Object>, Map<String, Object>> mapping,
      Function<Map<String, Object>, String> identity,
      Consumer<Map<String, Object>> validate) {
    if (input == null) throw invalid(502, "查询未返回列表");
    List<Map<String, Object>> out = new ArrayList<>();
    Set<String> keys = new HashSet<>();
    for (Map<String, Object> raw : input) {
      Map<String, Object> row = mapping.apply(raw);
      validate.accept(row);
      if (!keys.add(identity.apply(row))) throw invalid(502, "返回重复业务标识");
      out.add(row);
    }
    return out;
  }
}
