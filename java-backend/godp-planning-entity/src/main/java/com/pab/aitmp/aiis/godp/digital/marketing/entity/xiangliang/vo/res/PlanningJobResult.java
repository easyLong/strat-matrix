package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.res;

import java.util.*;

/** Pass completion is distinct from business completion; a receipt never means produced content. */
public final class PlanningJobResult {
  public String handler, status;
  public boolean needsNextTick;
  public final boolean businessComplete=false;
  public final Map<String,Long> nextCursors=new LinkedHashMap<>();
  public final List<Map<String,Object>> phases=new ArrayList<>();
}
