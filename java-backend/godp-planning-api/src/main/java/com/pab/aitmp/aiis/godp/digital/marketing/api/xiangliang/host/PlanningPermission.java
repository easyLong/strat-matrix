package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host;
import java.lang.annotation.*;

/** Capability metadata only. HostAccess performs real authorization; this never grants access. */
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE,ElementType.METHOD})
public @interface PlanningPermission {
  String REQUEST_ATTRIBUTE="planning.required-capabilities";
  String[] value();
}
