package com.pab.aitmp.aiis.godp.planning.entity.vo.req;

import com.fasterxml.jackson.annotation.JsonAlias;
import javax.validation.Valid;
import javax.validation.constraints.Min;
import javax.validation.constraints.NotNull;

/** Standalone business configuration; combined releases remain the normal write entry. */
public final class BusinessConfigSaveRequest {
  @Valid @NotNull public BusinessPlanningConfig config;
  @JsonAlias("expected_version") @NotNull @Min(0) public Integer expectedVersion;
}
