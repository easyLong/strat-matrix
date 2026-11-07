package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PlanningItemReadRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("slot_id") public String slotId;
  @TableField("account_id") public String accountId;
  @TableField("publish_date") public String publishDate;
  @TableField("publish_week") public String publishWeek;
  @TableField("payload") public String payload;
  @TableField("content_status") public String contentStatus;
  @TableField("runtime_active") public String runtimeActive;
  @TableField("plan_type") public String planType;
  @TableField("cycle_start") public String cycleStart;
  @TableField("cycle_end") public String cycleEnd;
  @TableField("topic_id") public String topicId;
  @TableField("topic_type") public String topicType;
  @TableField("content_type") public String contentType;
  @TableField("slot_type") public String slotType;
  @TableField("content_role") public String contentRole;
  @TableField("account_name") public String accountName;
  @TableField("owner_um") public String ownerUm;
  @TableField("organization") public String organization;
  @TableField("platform") public String platform;
  @TableField("account_type") public String accountType;
  @TableField("lifecycle_stage") public String lifecycleStage;
  @TableField("id") public Long id;
  @TableField("batch_id") public Long batchId;
  @TableField("version") public Integer version;
  @TableField("sort_millis") public Long sortMillis;
  @TableField("followers") public Long followers;
}
