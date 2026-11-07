package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import java.util.*;
import org.apache.ibatis.annotations.Param;

/** Read-only SQL boundary. Bind only to the host datasource that owns the original facts. */
public interface BankSourceMapper {
  Long countAccounts(@Param("query") BankSourceContracts.Accounts query);

  List<Map<String, Object>> accounts(@Param("query") BankSourceContracts.Accounts query);

  Long countTopics(@Param("query") BankSourceContracts.Topics query);

  List<Map<String, Object>> topics(@Param("query") BankSourceContracts.Topics query);

  Long countMarketingContents(@Param("query") BankSourceContracts.Marketing query);

  List<Map<String, Object>> marketingContents(@Param("query") BankSourceContracts.Marketing query);

  List<Map<String, Object>> effectiveMarketing(@Param("query") BankSourceContracts.Placement query);

  List<Map<String, Object>> productionStatus(@Param("query") BankSourceContracts.Production query);

  List<Map<String, Object>> marketingStatus(
      @Param("query") BankSourceContracts.MarketingStatus query);

  List<Map<String, Object>> approvedDemandContents(
      @Param("query") BankSourceContracts.ApprovedDemand query);
}
