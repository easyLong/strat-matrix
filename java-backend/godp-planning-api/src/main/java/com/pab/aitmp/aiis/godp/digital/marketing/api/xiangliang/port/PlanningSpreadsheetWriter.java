package com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port;
import java.util.List;

/** Host may supply its approved Excel writer; query scope and report columns stay in the service. */
public interface PlanningSpreadsheetWriter {
  byte[] write(List<String> headers, List<List<String>> rows);
}
