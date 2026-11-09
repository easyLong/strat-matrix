package com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.row.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.command.*;

import java.util.*;
import org.apache.ibatis.annotations.Param;

public interface ConfigReleaseMapper {
  PlanningConfigReleaseEntity current();

  PlanningConfigReleaseEntity pending();

  PlanningConfigReleaseEntity locked(@Param("id") String id);

  PlanningConfigReleaseEntity version(@Param("version") int version);

  List<PlanningConfigReleaseEntity> versions(@Param("limit") int limit);

  int insert(ConfigReleaseInsert command);

  int complete(
      @Param("id") String id,
      @Param("algorithmVersion") int algorithmVersion,
      @Param("configJson") String configJson);

  int reject(@Param("id") String id, @Param("error") String error);
}
