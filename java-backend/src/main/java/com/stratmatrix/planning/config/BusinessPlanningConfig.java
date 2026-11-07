package com.stratmatrix.planning.config;

import com.stratmatrix.planning.api.PlanningValidationException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Arrays;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.regex.Pattern;

/** Business-owned planning and content production settings shown in AI planning configuration. */
public class BusinessPlanningConfig {
  private static final Pattern TIME = Pattern.compile("(?:[01][0-9]|2[0-3]):[0-5][0-9]");
  public List<Integer> planning_days;
  public Integer schedule_day;
  public String schedule_time;
  public Integer marketing_max;
  public Integer hotspot_ratio;
  public Map<String, Integer> content_production_lead_days = new LinkedHashMap<>();

  public void validate() {
    if (planning_days == null || planning_days.isEmpty() || planning_days.size() > 7)
      throw new PlanningValidationException("每周策划日至少选择一天");
    Set<Integer> unique = new LinkedHashSet<>(planning_days);
    if (unique.size() != planning_days.size()
        || unique.stream().anyMatch(d -> d == null || d < 1 || d > 7))
      throw new PlanningValidationException("每周策划日须为周一至周日且不可重复");
    if (schedule_day == null
        || schedule_day < 1
        || schedule_day > 7
        || schedule_time == null
        || !TIME.matcher(schedule_time).matches())
      throw new PlanningValidationException("自动策划调度时间无效");
    if (marketing_max == null
        || marketing_max < 0
        || marketing_max > 10000
        || hotspot_ratio == null
        || hotspot_ratio < 0
        || hotspot_ratio > 100) throw new PlanningValidationException("营销上限或热点选题占比无效");
    if (content_production_lead_days == null) content_production_lead_days = new LinkedHashMap<>();
    Set<String> types = new LinkedHashSet<>(Arrays.asList("ordinary", "marketing", "hotspot"));
    for (Map.Entry<String, Integer> entry : content_production_lead_days.entrySet()) {
      Integer days = entry.getValue();
      if (!types.contains(entry.getKey()) || days != null && (days < 0 || days > 365))
        throw new PlanningValidationException("内容生产提前天数须为0至365的整数，选题类型须为普通、营销或热点");
    }
    content_production_lead_days = new LinkedHashMap<>(content_production_lead_days);
    planning_days = new ArrayList<>(unique);
    planning_days.sort(Integer::compareTo);
  }

  public String daysText() {
    StringBuilder out = new StringBuilder();
    for (Integer day : planning_days) {
      if (out.length() > 0) out.append(',');
      out.append(day);
    }
    return out.toString();
  }

  @com.fasterxml.jackson.annotation.JsonIgnore
  public String getProductionLeadDaysJson() {
    return com.stratmatrix.planning.manual.Json.write(content_production_lead_days);
  }

  public static BusinessPlanningConfig from(BusinessPlanningConfigRow row) {
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = new ArrayList<>();
    for (String day : row.planningDays.split(",")) config.planning_days.add(Integer.parseInt(day));
    config.schedule_day = row.scheduleDay;
    config.schedule_time = row.scheduleTime;
    config.marketing_max = row.marketingMax;
    config.hotspot_ratio = row.hotspotRatio;
    if (row.productionLeadDaysJson != null) {
      try {
        config.content_production_lead_days = new ObjectMapper().readValue(
            row.productionLeadDaysJson, new TypeReference<Map<String, Integer>>() {});
      } catch (Exception invalid) {
        throw new IllegalStateException("内容生产提前天数配置格式异常", invalid);
      }
    }
    return config;
  }
}
