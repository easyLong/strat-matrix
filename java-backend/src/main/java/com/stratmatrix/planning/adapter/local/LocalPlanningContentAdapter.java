package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.content.PlanningContentPort;
import com.stratmatrix.planning.manual.AccountSnapshotView;
import com.stratmatrix.planning.manual.BusinessException;
import com.stratmatrix.planning.source.SourceFacts;
import java.time.*;
import java.util.*;

/**
 * External-development fixture bridge only. Bank implementations query their Java services
 * directly.
 */
public final class LocalPlanningContentAdapter implements PlanningContentPort {
  private final SourceFacts facts;

  public LocalPlanningContentAdapter(SourceFacts facts) {
    this.facts = facts;
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
      Map<String, Object> response =
          path.equals("topics") ? facts.topics(body) : facts.marketingContents(body);
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
        // Validity is checked against each slot's publish date, not the T-1 scanning instant.
        pages("topics", map("source", "热点", "available_only", true)))
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
    for (Map<String, Object> c : pages("marketing", map("account_id", account)))
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
        rows(facts.effectiveMarketing(map("account_id", account, "publish_date", date.toString())));
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
    Object response = facts.approvedDemandContents(map("task_code", taskCode));
    if (!(response instanceof List)) throw new BusinessException(502, "营销分配查询未返回列表");
    List<Map<String, Object>> result = new ArrayList<>();
    for (Map<String, Object> content : rows(response)) {
      if (!taskCode.equals(text(content, "task_code")))
        throw new BusinessException(502, "营销分配结果不属于当前需求");
      String accountId = text(content, "account_id");
      List<Map<String, Object>> accounts =
          rows(
              facts
                  .accounts(map("account_ids", Collections.singletonList(accountId)))
                  .get("items"));
      if (accounts.size() != 1 || !accountId.equals(text(accounts.get(0), "account_id")))
        throw new BusinessException(502, "营销分配账号不可参与策划或不存在");
      Map<String, Object> row = new LinkedHashMap<>(content);
      row.put("account_snapshot", AccountSnapshotView.from(map("source_payload", accounts.get(0))));
      result.add(row);
    }
    return result;
  }
}
