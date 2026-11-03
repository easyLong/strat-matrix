package com.stratmatrix.planning.adapter.local;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.adapter.python.CatalogProjectionPythonClient;
import com.stratmatrix.planning.manual.*;
import com.stratmatrix.planning.source.SourceFacts;
import java.util.*;

/**
 * Local Source port: Java owns raw facts, Python only derives algorithm fields from supplied DTOs.
 */
public final class OutsideSourceAdapter implements ManualPorts.Source {
  private final SourceFacts facts;
  private final CatalogProjectionPythonClient algorithm;

  public OutsideSourceAdapter(SourceFacts facts, CatalogProjectionPythonClient algorithm) {
    this.facts = facts;
    this.algorithm = algorithm;
  }

  private List<Map<String, Object>> collect(boolean accounts, List<String> ids, int limit) {
    List<Map<String, Object>> result = new ArrayList<>();
    List<List<String>> chunks = new ArrayList<>();
    if (ids == null) chunks.add(null);
    else
      for (int start = 0; start < ids.size(); start += 500)
        chunks.add(ids.subList(start, Math.min(ids.size(), start + 500)));
    for (List<String> chunk : chunks) {
      for (int page = 1; ; page++) {
        Map<String, Object> q =
            map("page_no", page, "page_size", 500, accounts ? "account_ids" : "topic_ids", chunk);
        Map<String, Object> response = accounts ? facts.accounts(q) : facts.topics(q);
        List<Map<String, Object>> items = rows(response.get("items"));
        result.addAll(items);
        if (result.size() >= limit) return result.subList(0, limit);
        if ((long) page * 500 >= number(response, "total")) break;
        if (items.isEmpty()) throw new BusinessException(502, "Java模拟资料分页不完整");
      }
    }
    return result;
  }

  private Map<String, Object> project(
      List<String> accounts, List<String> topics, boolean available) {
    return algorithm.project(
        collect(true, accounts, 1000), collect(false, topics, 1000), available);
  }

  public List<Map<String, Object>> accountOptions(int limit, boolean includeDisabled) {
    return rows(
        algorithm
            .project(collect(true, null, limit), Collections.emptyList(), true)
            .get("accounts"));
  }

  public Map<String, Object> sourceAccounts(List<String> ids) {
    return project(ids, Collections.emptyList(), true);
  }

  public List<Map<String, Object>> topicCandidates(int limit) {
    // Apply availability before limiting, so expired records do not hide later eligible records.
    return rows(
            algorithm
                .project(Collections.emptyList(), collect(false, null, 1000), true)
                .get("topics"))
        .stream()
        .limit(limit)
        .collect(java.util.stream.Collectors.toList());
  }

  public Map<String, Object> topicDetail(String id, String type) {
    for (Map<String, Object> row :
        rows(project(Collections.emptyList(), Collections.singletonList(id), false).get("topics")))
      if (type == null || type.equals(row.get("topic_type"))) return row;
    throw new BusinessException(404, "选题不存在");
  }

  public Map<String, Object> snapshot(List<String> accounts, List<String> topics) {
    return project(accounts, topics, true);
  }

  public Set<String> historicalPlanned(String date) {
    return Collections.emptySet();
  }

  public Set<String> historicalReserved(String date) {
    return Collections.emptySet();
  }
}
