package com.stratmatrix.planning.auto;

import static com.stratmatrix.planning.manual.Json.*;

import com.stratmatrix.planning.config.BusinessPlanningConfig;
import com.stratmatrix.planning.manual.BusinessException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.util.*;

/** Validates the cross-language proposal before any business rows are inserted. */
public final class AutoProposalValidator {
  public Map<String, Object> validate(Map<String, Object> task, Map<String, Object> envelope) {
    require(envelope != null && number(envelope, "schema_version") == 1, "提案契约版本无效");
    String raw = text(envelope, "proposal_json"), hash = text(envelope, "proposal_hash");
    require(hash.matches("[a-f0-9]{64}") && hash.equals(sha256(raw)), "算法提案指纹不一致");
    Map<String, Object> p = read(raw);
    require(
        number(p, "schema_version") == 1 && "ordinary_only".equals(p.get("planning_scope")),
        "提案范围或版本不支持");
    require(
        number(p, "pipeline_id") == number(task, "pipeline_id")
            && number(p, "business_config_version") == number(task, "business_config_version"),
        "提案任务或业务配置版本不一致");
    Map<String, Object> frozen = read(text(task, "business_config_json"));
    require(frozen.equals(object(p.get("business_config"))), "提案业务配置快照不一致");
    BusinessPlanningConfig config;
    try {
      config =
          new com.fasterxml.jackson.databind.ObjectMapper()
              .convertValue(frozen, BusinessPlanningConfig.class);
      config.validate();
    } catch (RuntimeException e) {
      throw invalid("冻结业务配置无效");
    }
    LocalDate start = LocalDate.parse(text(task, "cycle_start"));
    LocalDate end = LocalDate.parse(text(task, "cycle_end"));
    require(
        start.getDayOfWeek().getValue() == 1
            && start.plusDays(6).equals(end)
            && start.toString().equals(text(p, "cycle_start"))
            && end.toString().equals(text(p, "cycle_end")),
        "提案周期不一致");
    require(
        number(p, "policy_id") > 0
            && number(p, "matching_task_id") > 0
            && text(p, "policy_hash").matches("[a-f0-9]{64}")
            && text(p, "matching_result_hash").matches("[a-f0-9]{64}"),
        "算法版本凭证不完整");
    Map<String, Object> accounts = object(p.get("accounts"));
    List<Map<String, Object>> slots = rows(p.get("slots"));
    require(
        !accounts.isEmpty()
            && accounts.size() <= 2000
            && slots.size() == accounts.size() * config.planning_days.size(),
        "提案账号或策划条数不完整");
    for (Map.Entry<String, Object> entry : accounts.entrySet()) {
      Map<String, Object> a = object(entry.getValue());
      require(
          !entry.getKey().isEmpty()
              && entry.getKey().length() <= 64
              && entry.getKey().equals(text(a, "account_id"))
              && !text(a, "account_name").trim().isEmpty(),
          "账号快照不完整");
    }
    Set<String> ids = new HashSet<>(), positions = new HashSet<>();
    int hotspots = 0;
    for (Map<String, Object> slot : slots) {
      String account = text(slot, "account_id"), id = text(slot, "slot_id");
      require(
          accounts.containsKey(account) && !id.isEmpty() && id.length() <= 128 && ids.add(id),
          "槽位账号或编号无效／重复");
      LocalDate date = LocalDate.parse(text(slot, "publish_date"));
      require(
          !date.isBefore(start)
              && !date.isAfter(end)
              && config.planning_days.contains(date.getDayOfWeek().getValue())
              && positions.add(account + "|" + date),
          "槽位日期无效／重复");
      require(
          Arrays.asList("流量", "转化").contains(slot.get("content_role"))
              && !text(slot, "lifecycle_stage").isEmpty(),
          "槽位经营信息缺失");
      String type = text(slot, "slot_type");
      if ("hotspot".equals(type)) {
        require(text(slot, "topic_id").isEmpty(), "热点空槽不能提前绑定选题");
        Map<String, Object> fallback =
            object(object(p.get("hotspot_fallbacks")).get(account + "|" + date));
        require(
            !text(fallback, "topic_id").isEmpty() && !text(fallback, "title").isEmpty(),
            "热点槽位缺少冻结普通兜底选题");
        hotspots++;
      } else {
        require(
            "regular".equals(type)
                && "普通".equals(slot.get("topic_type"))
                && !text(slot, "topic_id").isEmpty()
                && text(slot, "topic_id").length() <= 64
                && !text(slot, "topic_title").trim().isEmpty(),
            "普通槽位选题不完整");
      }
    }
    require(
        hotspots == number(p, "hotspot_slots")
            && hotspots == (slots.size() * config.hotspot_ratio + 50) / 100,
        "热点槽位比例不一致");
    return p;
  }

  public static String sha256(String raw) {
    try {
      byte[] bytes =
          MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));
      StringBuilder out = new StringBuilder();
      for (byte b : bytes) out.append(String.format("%02x", b & 255));
      return out.toString();
    } catch (java.security.NoSuchAlgorithmException impossible) {
      throw new IllegalStateException(impossible);
    }
  }

  private static void require(boolean valid, String message) {
    if (!valid) throw invalid(message);
  }

  private static BusinessException invalid(String message) {
    return new BusinessException(502, message);
  }
}
