package com.stratmatrix.planning.config;

/** MyBatis row for current and historical business planning configuration. */
public class BusinessPlanningConfigRow {
  public int version;
  public String planningDays;
  public int scheduleDay;
  public String scheduleTime;
  public int marketingMax;
  public int hotspotRatio;
  public String action;
  public Integer sourceVersion;
  public String createdBy;
  public String createdAt;
  public String updatedBy;
  public String updatedAt;
}
