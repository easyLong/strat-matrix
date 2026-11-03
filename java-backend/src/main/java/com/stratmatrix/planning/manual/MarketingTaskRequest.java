package com.stratmatrix.planning.manual;

import java.util.UUID;
import javax.validation.constraints.*;

/** One undated marketing topic and the number of content items to allocate. */
public class MarketingTaskRequest {
  @NotNull public UUID request_id;
  @NotBlank @Size(max = 120) public String task_name;
  @NotBlank @Size(max = 64) public String topic_id;
  @NotNull @Min(1) @Max(1000) public Integer allocation_count;
}
