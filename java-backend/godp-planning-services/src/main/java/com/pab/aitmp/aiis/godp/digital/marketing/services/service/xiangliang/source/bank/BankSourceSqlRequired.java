package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

/** XML guard: an unfinished site query must fail explicitly, not return fake empty data. */
public final class BankSourceSqlRequired {
  private BankSourceSqlRequired() {}

  public static String missing(String capability) {
    throw BankSourceQueries.missing(capability);
  }
}
