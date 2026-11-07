package com.pab.aitmp.aiis.godp.planning.entity.context;

import java.util.*;

/** Immutable trusted host facts. Carrying scope does not itself enforce SQL data permissions. */
public final class PlanningRequestContext {
  public enum Scope {
    UNSPECIFIED,
    NONE,
    ORGANIZATIONS,
    ALL
  }

  public final String userUm, traceId;
  public final Scope scope;
  public final Set<String> organizationCodes;

  public PlanningRequestContext(
      String userUm, Scope scope, Collection<String> organizationCodes, String traceId) {
    this.userUm = text(userUm, 50, "可信操作人");
    this.scope = Objects.requireNonNull(scope, "数据范围");
    LinkedHashSet<String> codes = new LinkedHashSet<>();
    for (String code : Objects.requireNonNull(organizationCodes, "机构范围"))
      codes.add(text(code, 128, "机构代码"));
    if ((scope == Scope.ORGANIZATIONS) == codes.isEmpty())
      throw new IllegalArgumentException("机构范围与范围类型不一致");
    this.organizationCodes = Collections.unmodifiableSet(codes);
    this.traceId = traceId == null ? UUID.randomUUID().toString() : text(traceId, 128, "追踪号");
    if (!this.traceId.matches("[A-Za-z0-9._:-]+")) throw new IllegalArgumentException("追踪号格式无效");
  }

  public static PlanningRequestContext identity(String um) {
    return new PlanningRequestContext(um, Scope.UNSPECIFIED, Collections.emptySet(), null);
  }

  private static String text(String value, int max, String label) {
    if (value == null
        || value.trim().isEmpty()
        || !value.equals(value.trim())
        || value.length() > max
        || value.chars().anyMatch(Character::isISOControl))
      throw new IllegalArgumentException(label + "无效");
    return value;
  }
}
