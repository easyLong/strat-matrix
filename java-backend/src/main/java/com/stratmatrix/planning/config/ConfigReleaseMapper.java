package com.stratmatrix.planning.config;

import java.util.*;
import org.apache.ibatis.annotations.Param;

public interface ConfigReleaseMapper {
  Map<String, Object> current();

  Map<String, Object> pending();

  Map<String, Object> locked(@Param("id") String id);

  Map<String, Object> version(@Param("version") int version);

  List<Map<String, Object>> versions(@Param("limit") int limit);

  int insert(Map<String, Object> command);

  int complete(
      @Param("id") String id,
      @Param("algorithmVersion") int algorithmVersion,
      @Param("configJson") String configJson);

  int reject(@Param("id") String id, @Param("error") String error);
}
