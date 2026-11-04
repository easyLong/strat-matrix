package com.stratmatrix.planning.adapter.local;

import com.stratmatrix.planning.adapter.python.CatalogProjectionPythonClient;
import com.stratmatrix.planning.source.SourceFacts;

/** Compatibility name for outside fixtures; hosts use source.SourceCatalogAdapter. */
public final class OutsideSourceAdapter
    extends com.stratmatrix.planning.source.SourceCatalogAdapter {
  public OutsideSourceAdapter(SourceFacts facts, CatalogProjectionPythonClient algorithm) {
    super(facts, algorithm);
  }
}
