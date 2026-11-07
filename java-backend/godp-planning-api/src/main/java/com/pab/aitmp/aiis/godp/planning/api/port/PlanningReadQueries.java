package com.pab.aitmp.aiis.godp.planning.api.port;

import java.util.*;

public interface PlanningReadQueries {
  Map<String, Object> plans(Map<String, Object> query);

  Map<String, Object> accounts(Map<String, Object> query);

  Map<String, Object> periods(Map<String, Object> query);

  Map<String, Object> tasks(Map<String, Object> query);

  List<Map<String, Object>> context(Map<String, Object> query);

  List<Map<String, Object>> records(Map<String, Object> query);

  List<Map<String, Object>> failures(Map<String, Object> query);

  Map<String, Object> archivedTask(String code);

  Map<String, Map<String, Object>> latestOperations(List<Long> ids);
}
