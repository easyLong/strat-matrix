package com.pab.aitmp.aiis.godp.planning.entity.error;

/** Explicit user-facing validation. Other IllegalArgumentException messages are not exposed. */
public class PlanningValidationException extends IllegalArgumentException {
  public PlanningValidationException(String message) {
    super(message);
  }
}
