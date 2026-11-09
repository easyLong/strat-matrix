package com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PythonRuntimeSettings;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PythonEndpoint;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

/** A host Apollo listener may replace the full snapshot; the business service never changes. */
public final class AtomicPythonSettings implements PythonRuntimeSettings {
  private final AtomicReference<PythonEndpoint> value;
  public AtomicPythonSettings(PythonEndpoint initial) {
    value=new AtomicReference<>(Objects.requireNonNull(initial));
  }
  public PythonEndpoint current() { return value.get(); }
  public void replace(PythonEndpoint next) { value.set(Objects.requireNonNull(next)); }
}
