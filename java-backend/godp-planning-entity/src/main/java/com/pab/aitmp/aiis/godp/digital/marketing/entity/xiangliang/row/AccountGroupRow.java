package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class AccountGroupRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("account_id") public String accountId;
  @TableField("slot_count") public Long slotCount;
  @TableField("cycle_count") public Long cycleCount;
  @TableField("latest_time") public Long latestTime;
}
