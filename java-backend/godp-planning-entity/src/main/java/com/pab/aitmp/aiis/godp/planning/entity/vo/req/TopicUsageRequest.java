package com.pab.aitmp.aiis.godp.planning.entity.vo.req;
import com.fasterxml.jackson.annotation.JsonAlias;
import com.pab.aitmp.aiis.godp.planning.entity.support.Json;
import java.util.*;
import javax.validation.constraints.*;

public final class TopicUsageRequest {
  @JsonAlias("topic_ids") @NotEmpty @Size(max=500) public List<@NotBlank @Size(max=64) String> topicIds;
  public Map<String,Object> values() { return Json.map("topic_ids",topicIds); }
}
