package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row;

import java.io.Serializable;
import com.baomidou.mybatisplus.annotation.TableField;

/** Typed SQL projection; JSON snapshot columns remain opaque text. */
public class TopicUsageRow implements Serializable {
  private static final long serialVersionUID=1L;
  @TableField("topic_id") public String topicId;
  @TableField("official_use_count") public Long officialUseCount;
}
