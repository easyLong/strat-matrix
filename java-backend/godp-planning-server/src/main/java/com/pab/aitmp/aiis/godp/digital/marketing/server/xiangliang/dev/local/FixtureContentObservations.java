package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentObservations;

/** Compatibility name for outside fixtures; hosts use content.ContentObservations. */
public final class FixtureContentObservations
    extends com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentObservations {
  public FixtureContentObservations(com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts facts) {
    super(facts);
  }
}
