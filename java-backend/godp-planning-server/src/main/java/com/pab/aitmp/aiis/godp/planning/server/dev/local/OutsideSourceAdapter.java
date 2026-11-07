package com.pab.aitmp.aiis.godp.planning.server.dev.local;

import com.pab.aitmp.aiis.godp.planning.services.source.SourceCatalogAdapter;

import com.pab.aitmp.aiis.godp.planning.client.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;

/** Compatibility name for outside fixtures; hosts use source.SourceCatalogAdapter. */
public final class OutsideSourceAdapter
    extends com.pab.aitmp.aiis.godp.planning.services.source.SourceCatalogAdapter {
  public OutsideSourceAdapter(SourceFacts facts, CatalogProjectionPythonClient algorithm) {
    super(facts, algorithm);
  }
}
