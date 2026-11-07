package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PeriodAccountCountRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("week_start") public String weekStart;
  @TableField("account_count") public Long accountCount;
  @TableField("auto_accounts") public Long autoAccounts;
  @TableField("manual_accounts") public Long manualAccounts;
  @TableField("completed_accounts") public Long completedAccounts;
}
