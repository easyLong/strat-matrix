package com.pab.aitmp.aiis.godp.planning.entity.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class PayloadRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("payload") public String payload;
}
