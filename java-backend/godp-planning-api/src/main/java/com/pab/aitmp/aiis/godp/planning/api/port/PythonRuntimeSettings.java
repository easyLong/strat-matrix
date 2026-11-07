package com.pab.aitmp.aiis.godp.planning.api.port;

import com.pab.aitmp.aiis.godp.planning.entity.vo.req.PythonEndpoint;

/** Host configuration plug: return one atomic URL/token snapshot per request. */
public interface PythonRuntimeSettings {
  PythonEndpoint current();
}
