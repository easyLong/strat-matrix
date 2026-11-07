package com.pab.aitmp.aiis.godp.planning.entity.vo.req;
import com.fasterxml.jackson.annotation.JsonAlias;
import javax.validation.constraints.*;

public final class ConfigSaveRequest {
  @NotNull public ConfigurationDocument config;
  @JsonAlias("expected_version") @NotNull @Min(0) public Integer expectedVersion;
}
