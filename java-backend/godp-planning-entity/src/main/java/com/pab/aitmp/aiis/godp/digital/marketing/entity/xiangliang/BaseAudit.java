package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.*;

/** Six bank audit fields; legacy millisecond timestamps remain separate columns. */
public abstract class BaseAudit implements Serializable {
  private static final long serialVersionUID = 1L;
  /** 主键ID；显式业务ID与数据库生成ID均保留原写法 */
  @TableId(value="id", type=IdType.AUTO)
  public Long id;
  /** 删除标志：N正常、Y删除 */
  @TableField("del_flag")
  public String delFlag;
  /** 创建人 */
  @TableField("created_by")
  public String createdBy;
  /** 修改人 */
  @TableField("updated_by")
  public String updatedBy;
  /** 创建时间 */
  @TableField("created_time")
  public java.time.LocalDateTime createdTime;
  /** 修改时间 */
  @TableField("updated_time")
  public java.time.LocalDateTime updatedTime;
}
