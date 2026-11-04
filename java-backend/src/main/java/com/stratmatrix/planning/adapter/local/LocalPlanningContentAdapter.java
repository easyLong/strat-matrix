package com.stratmatrix.planning.adapter.local;

/** Compatibility name for outside fixtures; hosts use content.ContentFactsAdapter. */
public final class LocalPlanningContentAdapter
    extends com.stratmatrix.planning.content.ContentFactsAdapter {
  public LocalPlanningContentAdapter(com.stratmatrix.planning.source.SourceFacts facts) {
    super(facts);
  }
}
