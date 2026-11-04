package com.stratmatrix.planning.host;

import com.stratmatrix.planning.context.PlanningRequestContext;
import javax.servlet.http.HttpServletRequest;

/** Optional host binding, called only after HostAccess authorization. Use trusted SSO context. */
public interface HostContextProvider {
  PlanningRequestContext resolve(HttpServletRequest request);
}
