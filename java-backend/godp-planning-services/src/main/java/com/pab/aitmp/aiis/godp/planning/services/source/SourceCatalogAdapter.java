package com.pab.aitmp.aiis.godp.planning.services.source;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;

import static com.pab.aitmp.aiis.godp.planning.entity.support.Json.*;

import com.pab.aitmp.aiis.godp.planning.client.python.CatalogProjectionPythonClient;
import java.util.*;

/**
 * Shared source port: Java owns raw facts, Python only derives algorithm fields from supplied DTOs.
 */
public class SourceCatalogAdapter implements ManualPorts.Source {
  private final SourcePageReader pages;
  private final CatalogProjectionPythonClient algorithm;

  public SourceCatalogAdapter(SourceFacts facts, CatalogProjectionPythonClient algorithm) {
    this.pages = new SourcePageReader(facts);
    this.algorithm = algorithm;
  }

  private List<Map<String, Object>> collect(boolean accounts, List<String> ids, int limit) {
    return pages.byIds(
        accounts ? SourcePageReader.Capability.ACCOUNTS : SourcePageReader.Capability.TOPICS,
        ids,
        limit);
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
