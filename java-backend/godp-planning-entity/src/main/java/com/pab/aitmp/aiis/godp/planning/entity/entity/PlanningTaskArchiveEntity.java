package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_task_archive，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_task_archive")
public class PlanningTaskArchiveEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 旧任务类型与编号组成的迁移唯一键 */
  @TableField("archive_key")
  public String archiveKey;
  /** 旧任务原始编号 */
  @TableField("source_id")
  public Long sourceId;
  /** 已确认的旧任务列表完整展示快照 */
  @TableField("payload")
  public String payload;
  /** 旧任务创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
}
