package com.pab.aitmp.aiis.godp.planning.api.host;

import com.pab.aitmp.aiis.godp.planning.entity.context.PlanningRequestContext;
import javax.servlet.http.HttpServletRequest;

/** Optional host binding, called only after HostAccess authorization. Use trusted SSO context. */
public interface HostContextProvider {
  PlanningRequestContext resolve(HttpServletRequest request);
}
