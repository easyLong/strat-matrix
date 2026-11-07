package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class ContentTypeCountRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("name") public String name;
  @TableField("amount") public Long amount;
}
