package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PlanningTaskReadRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("row_key") public String rowKey;
  @TableField("kind") public String kind;
  @TableField("payload") public String payload;
  @TableField("task_name") public String taskName;
  @TableField("batch_code") public String batchCode;
  @TableField("publish_date") public String publishDate;
  @TableField("created_by") public String createdBy;
  @TableField("content_status") public String contentStatus;
  @TableField("id") public Long id;
  @TableField("created_at") public Long createdAt;
}
