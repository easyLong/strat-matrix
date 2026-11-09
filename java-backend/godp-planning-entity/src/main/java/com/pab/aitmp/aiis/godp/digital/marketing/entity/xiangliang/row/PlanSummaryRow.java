package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PlanSummaryRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("accounts") public Long accounts;
  @TableField("batches") public Long batches;
  @TableField("topics") public Long topics;
}
