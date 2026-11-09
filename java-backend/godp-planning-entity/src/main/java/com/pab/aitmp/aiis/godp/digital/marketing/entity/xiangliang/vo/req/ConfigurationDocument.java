package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.databind.JsonNode;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import java.util.Map;

/** Algorithm-owned settings and label trees remain opaque documents; Java never rewrites their keys. */
public final class ConfigurationDocument {
  private final JsonNode value;
  @JsonCreator(mode=JsonCreator.Mode.DELEGATING)
  public ConfigurationDocument(JsonNode value) {
    if(value==null || !value.isObject()) throw new IllegalArgumentException("配置必须是对象");
    this.value=value.deepCopy();
  }
  public Map<String,Object> values() { return Json.read(value.toString()); }
}
