package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_batch，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_batch")
public class PlanningBatchEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 批次所属自然周的周一，用于时间列表数据库分页 */
  @TableField("week_start")
  public String weekStart;
  /** 结果发布状态：staging分批写入不可见、ready完整发布 */
  @TableField("write_state")
  public String writeState;
  /** 自动结果已提交的明细游标，分批恢复使用 */
  @TableField("write_cursor")
  public Integer writeCursor;
  /** 正式批次基本信息快照 */
  @TableField("payload")
  public String payload;
  /** 创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
}
