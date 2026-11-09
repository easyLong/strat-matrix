package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error;

public class BusinessException extends RuntimeException {
  public final int status;

  public BusinessException(int status, String message) {
    super(message);
    this.status = status;
  }
}
