package com.pab.aitmp.aiis.godp.planning.server.dev.local;

import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentObservations;

/** Compatibility name for outside fixtures; hosts use content.ContentObservations. */
public final class FixtureContentObservations
    extends com.pab.aitmp.aiis.godp.planning.services.content.ContentObservations {
  public FixtureContentObservations(com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts facts) {
    super(facts);
  }
}
