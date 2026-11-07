package com.pab.aitmp.aiis.godp.planning.api.host;
import java.lang.annotation.*;

/** Capability metadata only. HostAccess performs real authorization; this never grants access. */
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE,ElementType.METHOD})
public @interface PlanningPermission {
  String REQUEST_ATTRIBUTE="planning.required-capabilities";
  String[] value();
}
