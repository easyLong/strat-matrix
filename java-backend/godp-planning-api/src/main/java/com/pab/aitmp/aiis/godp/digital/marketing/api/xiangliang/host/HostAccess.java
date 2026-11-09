package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.host;

import javax.servlet.http.HttpServletRequest;

/**
 * Host supplies authentication, operation authorization and its data-scope context. No default
 * allow.
 */
public interface HostAccess {
  void authorize(HttpServletRequest request);
}
