package com.stratmatrix.planning.content;

import java.time.*;
import java.util.*;

/**
 * Host-owned read capabilities. Implement these against bank services; do not initiate content
 * production.
 */
public interface PlanningContentPort {
  List<Map<String, Object>> hotspots(Instant at);

  List<Map<String, Object>> approvedMarketing(String accountId);

  List<Map<String, Object>> effectiveMarketing(String accountId, LocalDate date);

  List<Map<String, Object>> approvedDemandContents(String taskCode);
}
