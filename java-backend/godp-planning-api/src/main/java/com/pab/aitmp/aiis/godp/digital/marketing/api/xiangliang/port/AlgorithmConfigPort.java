package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port;

import java.util.Map;

/** Host-replaceable algorithm configuration capabilities. */
public interface AlgorithmConfigPort {
  Map<String, Object> current();

  Map<String, Object> apply(
      String commandId, int expectedVersion, Map<String, Object> algorithmConfig, String actor);
}
