package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence;

import com.baomidou.mybatisplus.annotation.TableField;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.InsertCommand;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.PlanningQueryCriteria;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.*;
import java.util.function.ToIntFunction;

/**
 * Explicit SQL boundary: MyBatis uses typed rows/commands; existing snapshot algorithms use
 * column-keyed JSON objects. Entities never implement Map and are never passed to the page.
 */
public final class SqlRows {
  private static final ObjectMapper JSON = new ObjectMapper()
      .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
  private SqlRows() {}

  public static Map<String, Object> one(Object row) {
    if (row == null) return null;
    Map<String, Object> out = new LinkedHashMap<>();
    for (Field field : row.getClass().getFields()) {
      if (Modifier.isStatic(field.getModifiers())) continue;
      TableField column = field.getAnnotation(TableField.class);
      String key = column != null ? column.value()
          : field.getName().replaceAll("([a-z0-9])([A-Z])", "$1_$2").toLowerCase(Locale.ROOT);
      try {
        Object value = field.get(row);
        // Match MyBatis' original callSettersOnNulls=false map behavior for partial SELECTs.
        if (value != null) out.put(key, value);
      } catch (IllegalAccessException impossible) { throw new IllegalStateException(impossible); }
    }
    return out;
  }

  public static List<Map<String, Object>> list(Collection<?> rows) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (Object row : rows) out.add(one(row));
    return out;
  }

  public static PlanningQueryCriteria criteria(Map<String, Object> parameters) {
    return JSON.convertValue(parameters, PlanningQueryCriteria.class);
  }

  public static <T> int insert(Map<String, Object> values, Class<T> type, ToIntFunction<T> writer) {
    T command = JSON.convertValue(values, type);
    int changed = writer.applyAsInt(command);
    if (command instanceof InsertCommand && ((InsertCommand) command).id != null)
      values.put("id", ((InsertCommand) command).id);
    return changed;
  }
}
