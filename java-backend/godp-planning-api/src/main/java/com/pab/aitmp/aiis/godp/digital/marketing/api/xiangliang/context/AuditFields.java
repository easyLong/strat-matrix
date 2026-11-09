package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.context;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import java.util.Map;

/** Common MyBatis audit actor: trusted request UM, explicit server actor, or system job. */
public final class AuditFields {
  private AuditFields() {}

  public static String actor(Object parameter, boolean creating) {
    if (parameter != null && !(parameter instanceof Map))
      parameter = Json.read(Json.write(parameter));
    String value = RequestContexts.current().map(context -> context.userUm).orElse(null);
    if (value == null && parameter instanceof Map) {
      Map<?, ?> params = (Map<?, ?>) parameter;
      value = text(params, "actor");
      if (value == null) value = text(params, creating ? "createdBy" : "updatedBy");
      if (value == null
          && params.containsKey("payload")
          && params.get("payload") instanceof String) {
        Map<String, Object> payload = Json.read((String) params.get("payload"));
        value = text(payload, creating ? "created_by" : "updated_by");
      }
    }
    if (value == null) value = "system";
    if (value.length() > 50
        || value.trim().isEmpty()
        || !value.equals(value.trim())
        || value.chars().anyMatch(Character::isISOControl))
      throw new BusinessException(422, "操作人须为1至50个字符");
    return value;
  }

  private static String text(Map<?, ?> values, String key) {
    if (!values.containsKey(key)) return null;
    Object value = values.get(key);
    return value instanceof String && !((String) value).isEmpty() ? (String) value : null;
  }
}
