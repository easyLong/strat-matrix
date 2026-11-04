package com.stratmatrix.planning.config;

import com.stratmatrix.planning.api.PlanningValidationException;
import java.util.ArrayList;
import java.util.List;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Versioned authority for the four business-owned planning settings. */
public class BusinessPlanningConfigService {
  private final BusinessPlanningConfigMapper mapper;
  private final TransactionTemplate transactions;
  private final ConfigReleaseMapper releases;

  public BusinessPlanningConfigService(
      BusinessPlanningConfigMapper mapper, PlatformTransactionManager manager) {
    this(mapper, manager, null);
  }

  public BusinessPlanningConfigService(
      BusinessPlanningConfigMapper mapper,
      PlatformTransactionManager manager,
      ConfigReleaseMapper releases) {
    this.mapper = mapper;
    this.transactions = new TransactionTemplate(manager);
    this.releases = releases;
  }

  public Result current() {
    if (releases != null && releases.pending() != null)
      throw new ConfigConflict(409, "配置正在发布确认中，暂不发起新策划");
    BusinessPlanningConfigRow row = mapper.current();
    if (row == null) throw new ConfigConflict(409, "业务配置尚未从当前配置迁入");
    return new Result(row.version, row.updatedAt, BusinessPlanningConfig.from(row));
  }

  public List<Version> versions(int limit) {
    if (limit < 1 || limit > 100) throw new PlanningValidationException("历史版本数量无效");
    List<Version> out = new ArrayList<>();
    for (BusinessPlanningConfigRow row : mapper.versions(limit)) out.add(new Version(row));
    return out;
  }

  public Result save(BusinessPlanningConfig config, int expectedVersion, String actor) {
    return write(config, expectedVersion, actor, "保存", null);
  }

  public Result restore(int sourceVersion, int expectedVersion, String actor) {
    if (sourceVersion < 1) throw new PlanningValidationException("历史版本号无效");
    return transactions.execute(
        status -> {
          BusinessPlanningConfigRow source = mapper.version(sourceVersion);
          if (source == null) throw new ConfigConflict(404, "配置快照不存在");
          return saveInTransaction(
              BusinessPlanningConfig.from(source), expectedVersion, actor, "恢复", sourceVersion);
        });
  }

  private Result write(
      BusinessPlanningConfig config,
      int expectedVersion,
      String actor,
      String action,
      Integer sourceVersion) {
    if (config == null) throw new PlanningValidationException("配置内容不能为空");
    config.validate();
    if (actor == null || actor.trim().isEmpty()) throw new PlanningValidationException("操作人不能为空");
    if (expectedVersion < 0) throw new PlanningValidationException("配置版本号无效");
    try {
      return transactions.execute(
          status -> saveInTransaction(config, expectedVersion, actor, action, sourceVersion));
    } catch (DuplicateKeyException racedFirstInsert) {
      throw new ConfigConflict(409, "配置已被其他操作更新，请重新加载");
    }
  }

  private Result saveInTransaction(
      BusinessPlanningConfig config,
      int expectedVersion,
      String actor,
      String action,
      Integer sourceVersion) {
    config.validate();
    if (actor == null || actor.trim().isEmpty() || expectedVersion < 0)
      throw new PlanningValidationException("操作人或配置版本号无效");
    int changed =
        expectedVersion == 0
            ? mapper.insertCurrent(config, config.daysText(), actor)
            : mapper.updateCurrent(config, config.daysText(), expectedVersion, actor);
    if (changed != 1) throw new ConfigConflict(409, "配置已被其他操作更新，请重新加载");
    mapper.insertVersion(
        config, config.daysText(), expectedVersion + 1, action, sourceVersion, actor);
    return current();
  }

  public static final class Result {
    public final int version;
    public final String updated_at;
    public final BusinessPlanningConfig config;

    Result(int version, String updatedAt, BusinessPlanningConfig config) {
      this.version = version;
      this.updated_at = updatedAt;
      this.config = config;
    }
  }

  public static final class Version {
    public final int version;
    public final String action;
    public final Integer source_version;
    public final String created_at;
    public final String created_by;
    public final BusinessPlanningConfig config;

    Version(BusinessPlanningConfigRow row) {
      version = row.version;
      action = row.action;
      source_version = row.sourceVersion;
      created_at = row.createdAt;
      created_by = row.createdBy;
      config = BusinessPlanningConfig.from(row);
    }
  }

  public static final class ConfigConflict extends RuntimeException {
    public final int status;

    ConfigConflict(int status, String message) {
      super(message);
      this.status = status;
    }
  }
}
