package com.pab.aitmp.aiis.godp.planning.entity.vo.res;

import java.time.OffsetDateTime;

/** Return only after the content flow has been durably written or an identical write found. */
public final class ContentFlowReceipt {
  public enum Outcome { CREATED, UPDATED, ALREADY_PRESENT }

  public final String flowId;
  public final long planningItemId;
  public final int resultVersion;
  public final OffsetDateTime productionTime;
  public final int productionLeadDays;
  public final int configurationVersion;
  public final Outcome outcome;

  public ContentFlowReceipt(String flowId, long planningItemId, int resultVersion,
      OffsetDateTime productionTime, int productionLeadDays, int configurationVersion, Outcome outcome) {
    this.flowId = flowId;
    this.planningItemId = planningItemId;
    this.resultVersion = resultVersion;
    this.productionTime = productionTime;
    this.productionLeadDays = productionLeadDays;
    this.configurationVersion = configurationVersion;
    this.outcome = outcome;
  }
}
