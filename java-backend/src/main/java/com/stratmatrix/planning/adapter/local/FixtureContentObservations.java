package com.stratmatrix.planning.adapter.local;

/** Compatibility name for outside fixtures; hosts use content.ContentObservations. */
public final class FixtureContentObservations
    extends com.stratmatrix.planning.content.ContentObservations {
  public FixtureContentObservations(com.stratmatrix.planning.source.SourceFacts facts) {
    super(facts);
  }
}
