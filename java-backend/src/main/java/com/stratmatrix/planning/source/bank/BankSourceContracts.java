package com.stratmatrix.planning.source.bank;

import static com.stratmatrix.planning.source.bank.BankSourceValues.*;

import java.time.*;
import java.util.*;

/**
 * Immutable queries shared by SQL and existing-service readers. Public fields are MyBatis
 * properties.
 */
public final class BankSourceContracts {
  private BankSourceContracts() {}

  public static class PageQuery {
    public final int pageNo, pageSize;
    public final long offset;

    PageQuery(Map<String, Object> q) {
      Object page = value(q, "page_no", "页码", 422), size = value(q, "page_size", "每页条数", 422);
      pageNo = page == null ? 1 : (int) integer(page, "页码", 1, Integer.MAX_VALUE, 422);
      pageSize = size == null ? 100 : (int) integer(size, "每页条数", 1, 500, 422);
      offset = ((long) pageNo - 1) * pageSize;
    }
  }

  public static class UpdatedPage extends PageQuery {
    public final Instant updatedFrom, updatedTo;

    UpdatedPage(Map<String, Object> q) {
      super(q);
      updatedFrom = optionalTime(value(q, "updated_from", "更新开始时间", 422), "更新开始时间");
      updatedTo = optionalTime(value(q, "updated_to", "更新结束时间", 422), "更新结束时间");
      if (updatedFrom != null && updatedTo != null && !updatedFrom.isBefore(updatedTo))
        throw invalid(422, "更新时间范围");
    }
  }

  public static final class Accounts extends UpdatedPage {
    public final List<String> accountIds;

    public Accounts(Map<String, Object> q) {
      super(q);
      known(
          q, "page_no,页码,page_size,每页条数,updated_from,更新开始时间,updated_to,更新结束时间,account_ids,账号ID列表");
      accountIds = ids(value(q, "account_ids", "账号ID列表", 422), "账号ID列表", false);
    }
  }

  public static final class Topics extends UpdatedPage {
    public final List<String> topicIds;
    public final String source, topicType;
    public final boolean availableOnly;
    public final Instant validAt;

    public Topics(Map<String, Object> q) {
      super(q);
      known(
          q,
          "page_no,页码,page_size,每页条数,updated_from,更新开始时间,updated_to,更新结束时间,topic_ids,选题ID列表,source,选题来源,topic_type,选题类型,available_only,仅可用选题,valid_at,有效时点");
      topicIds = ids(value(q, "topic_ids", "选题ID列表", 422), "选题ID列表", false);
      source = choice(value(q, "source", "选题来源", 422), "选题来源", "普通", "热点");
      topicType = choice(value(q, "topic_type", "选题类型", 422), "选题类型", "营销", "非营销");
      Object available = value(q, "available_only", "仅可用选题", 422);
      availableOnly = available != null && bool(available, "仅可用选题", 422);
      validAt = optionalTime(value(q, "valid_at", "有效时点", 422), "有效时点");
    }
  }

  public static final class Marketing extends PageQuery {
    public final String accountId;

    public Marketing(Map<String, Object> q) {
      super(q);
      known(q, "page_no,页码,page_size,每页条数,account_id,账号ID");
      accountId = id(value(q, "account_id", "账号ID", 422), "账号ID", 422);
    }
  }

  public static final class Placement {
    public final String accountId;
    public final LocalDate publishDate;

    public Placement(Map<String, Object> q) {
      known(q, "account_id,账号ID,publish_date,投放日期");
      accountId = id(value(q, "account_id", "账号ID", 422), "账号ID", 422);
      publishDate = date(value(q, "publish_date", "投放日期", 422), "投放日期", 422);
    }
  }

  public static final class Production {
    public final List<String> slotIds;

    public Production(Map<String, Object> q) {
      known(q, "slot_ids");
      slotIds = ids(q.get("slot_ids"), "slot_ids", true);
    }
  }

  public static final class MarketingStatus {
    public final List<String> taskCodes;

    public MarketingStatus(Map<String, Object> q) {
      known(q, "task_codes");
      taskCodes = ids(q.get("task_codes"), "task_codes", true);
    }
  }

  public static final class ApprovedDemand {
    public final String taskCode;

    public ApprovedDemand(Map<String, Object> q) {
      known(q, "task_code");
      taskCode = id(q.get("task_code"), "task_code", 422);
    }
  }
  /** Raw reader page: rows use canonical SQL aliases or the Chinese contract aliases. */
  public static final class PageRows {
    public final long total;
    public final List<Map<String, Object>> items;

    public PageRows(long total, List<Map<String, Object>> items) {
      if (total < 0 || items == null) throw invalid(502, "分页结果");
      this.total = total;
      this.items = Collections.unmodifiableList(new ArrayList<>(items));
    }
  }

  private static Instant optionalTime(Object raw, String field) {
    return raw == null ? null : time(raw, field, BEIJING, 422);
  }

  private static String choice(Object raw, String field, String... options) {
    if (raw == null) return null;
    if (!(raw instanceof String) || !Arrays.asList(options).contains(raw))
      throw invalid(422, field);
    return (String) raw;
  }

  private static List<String> ids(Object raw, String field, boolean required) {
    if (raw == null && !required) return null;
    if (!(raw instanceof List)
        || ((List<?>) raw).size() > 500
        || required && ((List<?>) raw).isEmpty()) throw invalid(422, field);
    Set<String> result = new LinkedHashSet<>();
    for (Object item : (List<?>) raw) result.add(id(item, field, 422));
    return Collections.unmodifiableList(new ArrayList<>(result));
  }

  private static void known(Map<String, Object> q, String fields) {
    if (q == null) throw invalid(422, "查询对象不能为空");
    Set<String> known = new HashSet<>(Arrays.asList(fields.split(",")));
    if (!known.containsAll(q.keySet())) throw invalid(422, "存在未约定的查询字段");
  }
}
