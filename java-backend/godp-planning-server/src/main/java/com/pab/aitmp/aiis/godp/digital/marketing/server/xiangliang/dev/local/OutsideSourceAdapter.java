package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter;

import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;

/** Compatibility name for outside fixtures; hosts use source.SourceCatalogAdapter. */
public final class OutsideSourceAdapter
    extends com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter {
  public OutsideSourceAdapter(SourceFacts facts, CatalogProjectionPythonClient algorithm) {
    super(facts, algorithm);
  }
}
