package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;

import java.util.Objects;
import org.springframework.transaction.PlatformTransactionManager;

/** Explicitly binds this mapper and transaction manager to the same Java business database. */
public final class BusinessConfigDatabase {
  public final BusinessPlanningConfigMapper mapper;
  public final PlatformTransactionManager transactionManager;

  public BusinessConfigDatabase(BusinessPlanningConfigMapper mapper,
      PlatformTransactionManager transactionManager) {
    this.mapper = Objects.requireNonNull(mapper, "business config MyBatis mapper");
    this.transactionManager = Objects.requireNonNull(transactionManager,
        "business config transaction manager");
  }
}
