package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.content.PlanningContentPort;
import com.stratmatrix.planning.manual.BusinessException;
import java.time.*;
import java.util.*;

/**
 * External-development fixture bridge only. Bank implementations query their Java services
 * directly.
 */
public final class LocalPlanningContentAdapter implements PlanningContentPort {
  private final LocalPythonAdapter local;

  public LocalPlanningContentAdapter(LocalPythonAdapter local) {
    this.local = local;
  }

  private Object field(Map<String, Object> row, String english, String chinese) {
    return row.containsKey(english) ? row.get(english) : row.get(chinese);
  }

  private List<Map<String, Object>> pages(String path, Map<String, Object> request) {
    List<Map<String, Object>> all = new ArrayList<>();
    for (int page = 1; page <= 100; page++) {
      Map<String, Object> body = new LinkedHashMap<>(request);
      body.put("page_no", page);
      body.put("page_size", 500);
      Map<String, Object> response = object(local.call("POST", path, body));
      List<Map<String, Object>> items = rows(field(response, "items", "数据列表"));
      all.addAll(items);
      Object total = field(response, "total", "总数");
      if (total instanceof Number && all.size() >= ((Number) total).longValue()) return all;
      if (items.isEmpty()) throw new BusinessException(502, "本地资料分页返回不完整");
    }
    throw new BusinessException(503, "本地资料分页范围过大");
  }

  public List<Map<String, Object>> hotspots(Instant at) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> t :
        pages(
            "/api/integrations/bank/if02/topics/query",
            map("source", "热点", "available_only", true, "valid_at", at.toString())))
      out.add(
          map(
              "topic_id",
              field(t, "topic_id", "选题ID"),
              "title",
              field(t, "title", "选题标题"),
              "outline",
              field(t, "outline", "选题大纲"),
              "content_type",
              field(t, "content_type", "选题二级分类"),
              "valid_from",
              field(t, "valid_from", "有效开始时间"),
              "valid_to",
              field(t, "valid_to", "有效结束时间")));
    return out;
  }

  public List<Map<String, Object>> approvedMarketing(String account) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> c :
        pages("/api/integrations/bank/if03/marketing-contents/query", map("account_id", account)))
      out.add(
          map(
              "content_id",
              field(c, "content_id", "内容ID"),
              "account_id",
              field(c, "account_id", "绑定账号ID"),
              "title",
              field(c, "title", "内容标题"),
              "body",
              field(c, "body", "内容正文"),
              "approved_at",
              field(c, "approved_at", "审核通过时间")));
    return out;
  }

  public List<Map<String, Object>> effectiveMarketing(String account, LocalDate date) {
    List<Map<String, Object>> rows =
        rows(
            local.call(
                "POST",
                "/api/integrations/bank/if04/effective-marketing/query",
                map("account_id", account, "publish_date", date.toString())));
    if (rows.isEmpty()) return Collections.emptyList();
    List<Map<String, Object>> approved = approvedMarketing(account), out = new ArrayList<>();
    for (Map<String, Object> row : rows) {
      String content = String.valueOf(field(row, "content_id", "内容ID"));
      Map<String, Object> detail =
          approved.stream()
              .filter(c -> content.equals(c.get("content_id")))
              .findFirst()
              .orElseThrow(() -> new BusinessException(502, "有效营销内容缺少明细"));
      Map<String, Object> value = new LinkedHashMap<>(detail);
      value.put("publish_date", date.toString());
      out.add(value);
    }
    return out;
  }

  public List<Map<String, Object>> approvedDemandContents(String taskCode) {
    return Collections.emptyList();
  }
}
