package com.pab.aitmp.aiis.godp.planning.services.config;

import com.pab.aitmp.aiis.godp.planning.entity.entity.BusinessPlanningConfigRow;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.BusinessPlanningConfig;

import java.util.List;
import org.apache.ibatis.annotations.Param;

public interface BusinessPlanningConfigMapper {
  BusinessPlanningConfigRow current();

  BusinessPlanningConfigRow lockedCurrent();

  BusinessPlanningConfigRow version(@Param("version") int version);

  List<BusinessPlanningConfigRow> versions(@Param("limit") int limit);

  int insertCurrent(
      @Param("config") BusinessPlanningConfig config,
      @Param("days") String days,
      @Param("actor") String actor);

  int updateCurrent(
      @Param("config") BusinessPlanningConfig config,
      @Param("days") String days,
      @Param("expected") int expected,
      @Param("actor") String actor);

  int insertVersion(
      @Param("config") BusinessPlanningConfig config,
      @Param("days") String days,
      @Param("version") int version,
      @Param("action") String action,
      @Param("sourceVersion") Integer sourceVersion,
      @Param("actor") String actor);
}
