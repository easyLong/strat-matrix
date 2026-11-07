package com.stratmatrix.planning.manual;

import static com.stratmatrix.planning.manual.Json.text;

import java.time.*;
import java.time.format.DateTimeParseException;
import java.util.Map;

/** Manual topic validity uses Beijing calendar dates, inclusive of both boundaries. */
public final class TopicValidity {
  private static final ZoneId BEIJING = ZoneId.of("Asia/Shanghai");

  private TopicValidity() {}

  public static LocalDate today() {
    return LocalDate.now(BEIJING);
  }

  public static boolean includes(Map<String, Object> topic, LocalDate date) {
    LocalDate start = boundary(text(topic, "valid_from"));
    LocalDate end = boundary(text(topic, "valid_to"));
    return date != null && (start == null || !date.isBefore(start))
        && (end == null || !date.isAfter(end));
  }

  private static LocalDate boundary(String value) {
    if (value.isEmpty()) return null;
    try {
      if (value.length() == 10) return LocalDate.parse(value);
      try {
        return OffsetDateTime.parse(value).atZoneSameInstant(BEIJING).toLocalDate();
      } catch (DateTimeParseException noOffset) {
        return LocalDateTime.parse(value).toLocalDate();
      }
    } catch (DateTimeParseException invalid) {
      throw new BusinessException(502, "选题有效期数据格式异常，请联系管理员");
    }
  }
}
