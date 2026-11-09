package com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import java.util.*;
import org.apache.ibatis.annotations.Param;

public interface SlotCompletionMapper {
  List<PlanningItemEntity> hotspotsOnDate(
      @Param("publishDate") String publishDate, @Param("after") long after, @Param("limit") int limit);

  List<PlanningItemEntity> marketingSlots(@Param("after") long after, @Param("limit") int limit);

  int claim(@Param("kind") String kind, @Param("key") String key, @Param("item") long item);

  long claimed(@Param("kind") String kind, @Param("key") String key);

  int fill(
      @Param("id") long id,
      @Param("expected") int version,
      @Param("status") String status,
      @Param("payload") String payload);

  long contentLinks(
      @Param("account") String account, @Param("start") String start, @Param("end") String end);
}
