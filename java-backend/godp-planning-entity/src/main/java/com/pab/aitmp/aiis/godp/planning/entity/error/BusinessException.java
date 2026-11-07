package com.pab.aitmp.aiis.godp.planning.entity.error;

public class BusinessException extends RuntimeException {
  public final int status;

  public BusinessException(int status, String message) {
    super(message);
    this.status = status;
  }
}
