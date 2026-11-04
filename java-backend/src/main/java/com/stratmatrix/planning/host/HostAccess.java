package com.stratmatrix.planning.host;

import javax.servlet.http.HttpServletRequest;

/**
 * Host supplies authentication, operation authorization and its data-scope context. No default
 * allow.
 */
public interface HostAccess {
  void authorize(HttpServletRequest request);
}
