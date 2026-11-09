package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentFactsAdapter;

/** Compatibility name for outside fixtures; hosts use content.ContentFactsAdapter. */
public final class LocalPlanningContentAdapter
    extends com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentFactsAdapter {
  public LocalPlanningContentAdapter(com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts facts) {
    super(facts);
  }
}
