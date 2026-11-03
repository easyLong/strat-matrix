package com.stratmatrix.planning.query;

import java.util.*;

public interface PlanningQueryMapper {
  List<Map<String, Object>> records(Map<String, Object> p);

  List<Map<String, Object>> groupKeys(Map<String, Object> p);

  long groupCount(Map<String, Object> p);

  Map<String, Object> summary(Map<String, Object> p);

  List<Map<String, Object>> distribution(Map<String, Object> p);

  List<Map<String, Object>> accountGroups(Map<String, Object> p);

  long accountCount(Map<String, Object> p);

  List<Map<String, Object>> accountSnapshots(Map<String, Object> p);

  List<Map<String, Object>> facets(Map<String, Object> p);

  List<Map<String, Object>> periodKeys(Map<String, Object> p);

  long periodCount(Map<String, Object> p);

  List<Map<String, Object>> periodBatches(Map<String, Object> p);

  List<Map<String, Object>> periodAccounts(Map<String, Object> p);

  List<Map<String, Object>> tasks(Map<String, Object> p);

  long taskCount(Map<String, Object> p);

  List<Map<String, Object>> latestOperations(Map<String, Object> p);

  List<Map<String, Object>> failures(Map<String, Object> p);

  Map<String, Object> archivedTask(Map<String, Object> p);
}
