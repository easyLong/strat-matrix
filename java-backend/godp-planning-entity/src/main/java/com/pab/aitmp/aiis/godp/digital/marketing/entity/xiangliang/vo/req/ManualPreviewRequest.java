package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;

import java.time.LocalDate;
import java.util.*;
import javax.validation.constraints.*;

/** Existing Vue contract. Identity and source snapshots are resolved server-side. */
public class ManualPreviewRequest {
  @NotBlank
  @Size(max = 120)
  public String task_name;

  @NotNull public LocalDate publish_date;

  @NotEmpty
  @Size(max = 1000)
  public List<@NotBlank @Size(max = 64) String> account_ids;

  @NotEmpty
  @Size(max = 100)
  public List<@NotBlank @Size(max = 64) String> topic_ids;

  @Min(1)
  @Max(1000)
  public Integer target_count;

  public String content_mode = "non_marketing";

  @Size(max = 500)
  public String note = "";
}
