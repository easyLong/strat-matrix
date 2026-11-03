package com.stratmatrix.planning.manual;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;

/** JSON snapshots at the integration boundary; no ORM or host-private dependency. */
public final class Json {
  private static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();

  private Json() {}

  public static Map<String, Object> map(Object... fields) {
    Map<String, Object> out = new LinkedHashMap<>();
    for (int i = 0; i < fields.length; i += 2) out.put((String) fields[i], fields[i + 1]);
    return out;
  }

  public static String write(Object value) {
    try {
      return MAPPER.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalArgumentException("无法序列化业务快照", e);
    }
  }

  public static Map<String, Object> read(String value) {
    try {
      return MAPPER.readValue(value, new TypeReference<Map<String, Object>>() {});
    } catch (Exception e) {
      throw new IllegalArgumentException("业务快照格式无效", e);
    }
  }

  @SuppressWarnings("unchecked")
  public static Map<String, Object> object(Object value) {
    return value instanceof Map ? (Map<String, Object>) value : new LinkedHashMap<>();
  }

  @SuppressWarnings("unchecked")
  public static List<Map<String, Object>> rows(Object value) {
    return value instanceof List ? (List<Map<String, Object>>) value : new ArrayList<>();
  }

  public static String text(Map<String, Object> map, String key) {
    Object v = map.get(key);
    return v == null ? "" : v.toString();
  }

  public static long number(Map<String, Object> map, String key) {
    Object v = map.get(key);
    return v instanceof Number ? ((Number) v).longValue() : 0;
  }
}
