package com.pab.aitmp.aiis.godp.planning.entity.command;

/** Shared trusted audit input, never accepted directly from a page request. */
public abstract class InsertCommand {
  public Long id;
  public String actor, createdBy, updatedBy;
}
