package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;
import com.fasterxml.jackson.annotation.JsonAlias;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import java.util.Map;
import javax.validation.constraints.*;

public final class ReplacementRequest {
  @JsonAlias("new_topic_id") @NotBlank @Size(max=64) public String newTopicId;
  @JsonAlias("expected_version") @NotNull @Min(1) public Long expectedVersion;
  @Size(max=500) public String reason="";
  public Map<String,Object> values() { return Json.map("new_topic_id",newTopicId,"expected_version",expectedVersion,"reason",reason); }
}
