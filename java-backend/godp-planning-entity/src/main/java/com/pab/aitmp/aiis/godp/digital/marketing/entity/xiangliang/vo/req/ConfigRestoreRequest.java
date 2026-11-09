package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;

import javax.validation.constraints.Min;
import javax.validation.constraints.NotNull;

/** Restore requires the currently displayed configuration version in the JSON body. */
public final class ConfigRestoreRequest {
  @NotNull @Min(0) public Integer expectedVersion;
}
