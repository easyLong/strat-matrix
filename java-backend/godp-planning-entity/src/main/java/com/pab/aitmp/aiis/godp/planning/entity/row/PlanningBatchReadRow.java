package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PlanningBatchReadRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("payload") public String payload;
  @TableField("week_start") public String weekStart;
  @TableField("plan_type") public String planType;
  @TableField("cycle_start") public String cycleStart;
  @TableField("cycle_end") public String cycleEnd;
  @TableField("batch_code") public String batchCode;
  @TableField("task_name") public String taskName;
  @TableField("id") public Long id;
  @TableField("created_at") public Long createdAt;
  @TableField("account_count") public Long accountCount;
  @TableField("completed_count") public Long completedCount;
  @TableField("failed_count") public Long failedCount;
  @TableField("topic_count") public Long topicCount;
}
