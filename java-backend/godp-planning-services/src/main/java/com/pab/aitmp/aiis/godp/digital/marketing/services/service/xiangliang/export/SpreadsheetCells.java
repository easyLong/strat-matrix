package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.export;
public final class SpreadsheetCells {
  private SpreadsheetCells() {}
  public static String safe(String value) {
    if(value==null) return "";
    return value.trim().matches("(?s)^[=+@\\-].*") ? "'"+value:value;
  }
}
