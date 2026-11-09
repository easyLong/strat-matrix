package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.context.PlanningRequestContext;
import javax.servlet.http.HttpServletRequest;

/** Optional host binding, called only after HostAccess authorization. Use trusted SSO context. */
public interface HostContextProvider {
  PlanningRequestContext resolve(HttpServletRequest request);
}
