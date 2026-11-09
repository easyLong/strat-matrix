package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PythonEndpoint;

/** Host configuration plug: return one atomic URL/token snapshot per request. */
public interface PythonRuntimeSettings {
  PythonEndpoint current();
}
