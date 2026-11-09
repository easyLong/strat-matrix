package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PlanGroupRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("group_key") public String groupKey;
  @TableField("last_date") public String lastDate;
  @TableField("last_id") public Long lastId;
}
