package com.pab.aitmp.aiis.godp.planning.api.port;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;

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

  /**
   * Approved content and account allocation for a manual marketing demand; supplied by content
   * side.
   */
  default Object approvedDemandContents(Map<String, Object> query) {
    throw new com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException(503, "营销需求过审分配查询尚未接入");
  }
}
