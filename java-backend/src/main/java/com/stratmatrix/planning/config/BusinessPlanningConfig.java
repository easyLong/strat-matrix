package com.stratmatrix.planning.config;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

/** The four business-owned fields shown in AI planning configuration. */
public class BusinessPlanningConfig {
  private static final Pattern TIME = Pattern.compile("(?:[01][0-9]|2[0-3]):[0-5][0-9]");
  public List<Integer> planning_days;
  public Integer schedule_day;
  public String schedule_time;
  public Integer marketing_max;
  public Integer hotspot_ratio;

  public void validate() {
    if (planning_days == null || planning_days.isEmpty() || planning_days.size() > 7)
      throw new IllegalArgumentException("每周策划日至少选择一天");
    Set<Integer> unique = new LinkedHashSet<>(planning_days);
    if (unique.size() != planning_days.size() || unique.stream().anyMatch(d -> d == null || d < 1 || d > 7))
      throw new IllegalArgumentException("每周策划日须为周一至周日且不可重复");
    if (schedule_day == null || schedule_day < 1 || schedule_day > 7
        || schedule_time == null || !TIME.matcher(schedule_time).matches())
      throw new IllegalArgumentException("自动策划调度时间无效");
    if (marketing_max == null || marketing_max < 0 || marketing_max > 10000
        || hotspot_ratio == null || hotspot_ratio < 0 || hotspot_ratio > 100)
      throw new IllegalArgumentException("营销上限或热点选题占比无效");
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

  public static BusinessPlanningConfig from(BusinessPlanningConfigRow row) {
    BusinessPlanningConfig config = new BusinessPlanningConfig();
    config.planning_days = new ArrayList<>();
    for (String day : row.planningDays.split(",")) config.planning_days.add(Integer.parseInt(day));
    config.schedule_day = row.scheduleDay;
    config.schedule_time = row.scheduleTime;
    config.marketing_max = row.marketingMax;
    config.hotspot_ratio = row.hotspotRatio;
    return config;
  }
}
