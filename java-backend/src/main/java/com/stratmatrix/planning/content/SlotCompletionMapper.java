package com.stratmatrix.planning.content;

import java.util.*;
import org.apache.ibatis.annotations.Param;

public interface SlotCompletionMapper {
  List<Map<String, Object>> dueHotspots(
      @Param("cutoff") String cutoff, @Param("after") long after, @Param("limit") int limit);

  List<Map<String, Object>> marketingSlots(@Param("after") long after, @Param("limit") int limit);

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
