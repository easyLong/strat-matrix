package com.stratmatrix.planning.source;

import java.util.Map;

/**
 * Raw host-owned facts only. Outside reads fixtures; inside supplies SQL/service implementations.
 */
public interface SourceFacts {
  Map<String, Object> accounts(Map<String, Object> query);

  Map<String, Object> topics(Map<String, Object> query);

  Map<String, Object> marketingContents(Map<String, Object> query);

  Object effectiveMarketing(Map<String, Object> query);

  Object productionStatus(Map<String, Object> query);

  Object marketingStatus(Map<String, Object> query);
}
