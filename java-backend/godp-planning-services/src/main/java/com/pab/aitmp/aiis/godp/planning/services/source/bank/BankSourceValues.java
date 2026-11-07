package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import com.pab.aitmp.aiis.godp.planning.entity.error.BusinessException;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

/** Contract conversions only. No bank column names or private status-code guesses. */
final class BankSourceValues {
  static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");

  private BankSourceValues() {}

  static BusinessException invalid(int status, String field) {
    return new BusinessException(status, (status == 422 ? "资料查询参数无效：" : "行内资料返回不符合契约：") + field);
  }

  static Object value(Map<String, Object> values, String name, String alias, int status) {
    if (values == null) throw invalid(status, "对象不能为空");
    if (values.containsKey(name)
        && values.containsKey(alias)
        && !Objects.deepEquals(values.get(name), values.get(alias)))
      throw invalid(status, name + "与中文别名冲突");
    return values.containsKey(name) ? values.get(name) : values.get(alias);
  }

  static String text(Object value, String field, boolean required, int max, int status) {
    if (value == null) {
      if (required) throw invalid(status, field + "缺失");
      return "";
    }
    if (!(value instanceof CharSequence)) throw invalid(status, field + "应为文本");
    String result = value.toString();
    if ((required && result.trim().isEmpty()) || (max > 0 && result.length() > max))
      throw invalid(status, field);
    return result;
  }

  static String id(Object value, String field, int status) {
    String result = text(value, field, true, field.equals("slot_ids") ? 128 : 64, status);
    if (!result.equals(result.trim())) throw invalid(status, field + "不能含首尾空格");
    return result;
  }

  static long integer(Object raw, String field, long min, long max, int status) {
    if (raw == null || raw instanceof Boolean || (status == 422 && !(raw instanceof Number)))
      throw invalid(status, field);
    try {
      long value = new BigDecimal(raw.toString()).longValueExact();
      if (value < min || value > max) throw invalid(status, field);
      return value;
    } catch (NumberFormatException | ArithmeticException invalid) {
      throw invalid(status, field);
    }
  }

  static boolean bool(Object raw, String field, int status) {
    if (raw instanceof Boolean) return (Boolean) raw;
    if (status == 502) {
      if ("1".equals(String.valueOf(raw)) || "true".equalsIgnoreCase(String.valueOf(raw)))
        return true;
      if ("0".equals(String.valueOf(raw)) || "false".equalsIgnoreCase(String.valueOf(raw)))
        return false;
    }
    throw invalid(status, field + "应为布尔值");
  }

  static Instant time(Object raw, String field, ZoneId zone, int status) {
    try {
      if (raw instanceof Instant) return (Instant) raw;
      if (raw instanceof OffsetDateTime) return ((OffsetDateTime) raw).toInstant();
      if (raw instanceof ZonedDateTime) return ((ZonedDateTime) raw).toInstant();
      if (raw instanceof LocalDateTime) return ((LocalDateTime) raw).atZone(zone).toInstant();
      // JDBC DATETIME is a wall clock; the host declares its storage timezone explicitly.
      if (raw instanceof java.sql.Timestamp)
        return ((java.sql.Timestamp) raw).toLocalDateTime().atZone(zone).toInstant();
      if (raw instanceof java.util.Date && !(raw instanceof java.sql.Date))
        return ((java.util.Date) raw).toInstant();
      if (!(raw instanceof String)) throw invalid(status, field);
      String value = ((String) raw).replace(' ', 'T');
      try {
        return OffsetDateTime.parse(value).toInstant();
      } catch (java.time.format.DateTimeParseException noOffset) {
        return LocalDateTime.parse(value).atZone(zone).toInstant();
      }
    } catch (RuntimeException error) {
      throw invalid(status, field + "应为完整日期时间");
    }
  }

  static LocalDate date(Object raw, String field, int status) {
    try {
      if (raw instanceof LocalDate) return (LocalDate) raw;
      if (raw instanceof java.sql.Date) return ((java.sql.Date) raw).toLocalDate();
      if (!(raw instanceof String) || !((String) raw).matches("\\d{4}-\\d{2}-\\d{2}"))
        throw invalid(status, field);
      return LocalDate.parse((String) raw);
    } catch (RuntimeException error) {
      throw invalid(status, field + "应为年月日");
    }
  }

  static String iso(Instant value) {
    return value
        .atZone(BEIJING)
        .toOffsetDateTime()
        .format(java.time.format.DateTimeFormatter.ISO_OFFSET_DATE_TIME);
  }
}
