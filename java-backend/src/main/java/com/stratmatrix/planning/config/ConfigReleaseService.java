package com.stratmatrix.planning.config;

import static com.stratmatrix.planning.manual.Json.*;

import com.fasterxml.jackson.databind.*;
import com.stratmatrix.planning.auto.AutoProposalValidator;
import com.stratmatrix.planning.manual.BusinessException;
import java.time.Instant;
import java.util.*;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.HttpClientErrorException;

/**
 * Durable two-database publication: one page command, retryable algorithm apply, atomic business
 * release.
 */
public final class ConfigReleaseService {
  public static final Set<String> BUSINESS =
      new HashSet<>(
          Arrays.asList(
              "planning_days", "schedule_day", "schedule_time", "marketing_max", "hotspot_ratio"));
  private final ConfigReleaseMapper releases;
  private final BusinessPlanningConfigService business;
  private final BusinessConfigDatabase db;
  private final AlgorithmConfigPort algorithm;
  private final TransactionTemplate tx;
  private final ObjectMapper json =
      new ObjectMapper().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);

  public ConfigReleaseService(
      ConfigReleaseMapper releases,
      BusinessPlanningConfigService business,
      BusinessConfigDatabase db,
      AlgorithmConfigPort algorithm) {
    this.releases = releases;
    this.business = business;
    this.db = db;
    this.algorithm = algorithm;
    this.tx = new TransactionTemplate(db.transactionManager);
  }

  public void bootstrap() {
    if (releases.current() != null) return;
    Map<String, Object> legacy = algorithm.current();
    Map<String, Object> values = new LinkedHashMap<>(object(legacy.get("config")));
    if (values.isEmpty()) throw new BusinessException(502, "算法配置未返回完整对象");
    try {
      tx.execute(
          s -> {
            if (releases.current() != null) return null;
            BusinessPlanningConfigRow old = db.mapper.lockedCurrent();
            if (old == null) business.save(businessValues(values), 0, "configuration-migration");
            else values.putAll(read(write(BusinessPlanningConfig.from(old))));
            int version = Math.max(1, (int) number(legacy, "version"));
            releases.insert(
                map(
                    "id",
                    "CONFIG-IMPORT-" + version,
                    "version",
                    version,
                    "status",
                    "completed",
                    "hash",
                    hash(values),
                    "config",
                    write(values),
                    "businessVersion",
                    business.current().version,
                    "algorithmVersion",
                    number(legacy, "version"),
                    "actor",
                    "configuration-migration",
                    "time",
                    Instant.now().toString(),
                    "action",
                    "首次迁入",
                    "sourceVersion",
                    null));
            return null;
          });
    } catch (org.springframework.dao.DuplicateKeyException raced) {
      if (releases.current() == null) throw raced;
    }
  }

  public Map<String, Object> current() {
    bootstrap();
    if (releases.pending() != null) throw new BusinessException(409, "配置正在保存确认中，请稍后重试");
    return view(releases.current());
  }

  public List<Map<String, Object>> versions(int limit) {
    if (limit < 1 || limit > 100) throw new BusinessException(422, "历史配置数量无效");
    bootstrap();
    List<Map<String, Object>> out = new ArrayList<>();
    for (Map<String, Object> r : releases.versions(limit))
      out.add(
          map(
              "version",
              r.get("version"),
              "config",
              read(text(r, "config_json")),
              "action",
              r.get("action"),
              "source_version",
              r.get("source_version"),
              "created_at",
              r.get("created_at"),
              "created_by",
              r.get("created_by")));
    return out;
  }

  public Map<String, Object> restore(int version, int expected, String actor) {
    bootstrap();
    Map<String, Object> source = releases.version(version);
    if (source == null) throw new BusinessException(404, "配置历史不存在");
    return save(read(text(source, "config_json")), expected, actor, "恢复", version);
  }

  public Map<String, Object> save(Map<String, Object> values, int expected, String actor) {
    return save(values, expected, actor, "保存", null);
  }

  private Map<String, Object> save(
      Map<String, Object> values, int expected, String actor, String action, Integer source) {
    bootstrap();
    businessValues(values).validate();
    if (actor == null || actor.trim().isEmpty()) throw new BusinessException(422, "操作人不能为空");
    Map<String, Object> command =
        tx.execute(
            s -> {
              db.mapper.lockedCurrent();
              Map<String, Object> current = releases.current();
              if (number(current, "version") != expected)
                throw new BusinessException(409, "配置版本已变化，请重新加载");
              Map<String, Object> pending = releases.pending();
              if (pending != null) {
                if (!hash(values).equals(pending.get("request_hash")))
                  throw new BusinessException(409, "已有配置正在保存确认中");
                return pending;
              }
              Map<String, Object> c =
                  map(
                      "id",
                      "CONFIG-" + UUID.randomUUID(),
                      "version",
                      expected + 1,
                      "status",
                      "pending",
                      "hash",
                      hash(values),
                      "config",
                      write(values),
                      "businessVersion",
                      db.mapper.current().version,
                      "algorithmVersion",
                      current.get("algorithm_version"),
                      "actor",
                      actor,
                      "time",
                      Instant.now().toString(),
                      "action",
                      action,
                      "sourceVersion",
                      source);
              releases.insert(c);
              return releases.locked(text(c, "id"));
            });
    return apply(command);
  }

  public void advancePending() {
    Map<String, Object> pending = releases.pending();
    if (pending != null) apply(pending);
  }

  private Map<String, Object> apply(Map<String, Object> command) {
    String id = text(command, "command_id");
    Map<String, Object> full = read(text(command, "config_json"));
    Map<String, Object> algorithmValues = new LinkedHashMap<>(full);
    BUSINESS.forEach(algorithmValues::remove);
    Map<String, Object> result;
    try {
      result =
          algorithm.apply(
              id,
              (int) number(command, "algorithm_version"),
              algorithmValues,
              text(command, "created_by"));
    } catch (HttpClientErrorException invalid) {
      if (invalid.getRawStatusCode() == 409 || invalid.getRawStatusCode() == 422) {
        releases.reject(id, "算法配置校验或版本冲突");
        throw new BusinessException(invalid.getRawStatusCode(), "配置校验失败或版本冲突，请重新加载后重试");
      }
      throw new BusinessException(503, "配置已记录，等待算法服务确认，请稍后重试");
    } catch (RuntimeException unavailable) {
      throw new BusinessException(503, "配置已记录，等待算法服务确认，请稍后重试");
    }
    Map<String, Object> normalized = new LinkedHashMap<>(object(result.get("config")));
    if (normalized.isEmpty() || number(result, "version") < 1)
      throw new BusinessException(502, "算法配置确认数据无效");
    for (String key : BUSINESS) normalized.put(key, full.get(key));
    return tx.execute(
        s -> {
          db.mapper.lockedCurrent();
          Map<String, Object> locked = releases.locked(id);
          if ("completed".equals(locked.get("status"))) return view(locked);
          if (!"pending".equals(locked.get("status")))
            throw new BusinessException(409, "配置命令状态已变化");
          releases.complete(id, (int) number(result, "version"), write(normalized));
          business.save(
              businessValues(full),
              (int) number(locked, "business_expected_version"),
              text(locked, "created_by"));
          return view(releases.locked(id));
        });
  }

  private BusinessPlanningConfig businessValues(Map<String, Object> config) {
    Map<String, Object> fields = new LinkedHashMap<>();
    BUSINESS.forEach(k -> fields.put(k, config.get(k)));
    BusinessPlanningConfig value = json.convertValue(fields, BusinessPlanningConfig.class);
    value.validate();
    return value;
  }

  private String hash(Map<String, Object> values) {
    try {
      return AutoProposalValidator.sha256(json.writeValueAsString(values));
    } catch (Exception error) {
      throw new BusinessException(422, "配置格式无效");
    }
  }

  private Map<String, Object> view(Map<String, Object> r) {
    return map(
        "version",
        r.get("version"),
        "updated_at",
        r.get("created_at"),
        "config",
        read(text(r, "config_json")),
        "is_demo",
        false);
  }
}
