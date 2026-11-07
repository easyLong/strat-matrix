package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PeriodKeyRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("week_start") public String weekStart;
}
