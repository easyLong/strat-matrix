package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_manual_preview，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_manual_preview")
public class ManualPreviewEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** Java预览编号 */
  @TableField("preview_code")
  public String previewCode;
  /** 业务输入及账号选题冻结快照 */
  @TableField("payload")
  public String payload;
  /** 过期时间毫秒戳 */
  @TableField("expires_at")
  public Long expiresAt;
  /** 创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
}
