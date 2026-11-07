package com.pab.aitmp.aiis.godp.planning.server.dev.local;

import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentFactsAdapter;

/** Compatibility name for outside fixtures; hosts use content.ContentFactsAdapter. */
public final class LocalPlanningContentAdapter
    extends com.pab.aitmp.aiis.godp.planning.services.content.ContentFactsAdapter {
  public LocalPlanningContentAdapter(com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts facts) {
    super(facts);
  }
}
