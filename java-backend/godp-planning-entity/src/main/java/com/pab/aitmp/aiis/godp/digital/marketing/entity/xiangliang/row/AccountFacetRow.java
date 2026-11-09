package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class AccountFacetRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("organization") public String organization;
  @TableField("platform") public String platform;
  @TableField("lifecycle_stage") public String lifecycleStage;
}
