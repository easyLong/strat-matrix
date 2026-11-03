package com.stratmatrix.planning.manual;

import java.util.Objects;
import org.springframework.transaction.PlatformTransactionManager;

/** Host binding for the business MyBatis mapper and the matching transaction manager. */
public final class ManualDatabase {
  public final ManualMapper mapper;
  public final PlatformTransactionManager transactionManager;

  public ManualDatabase(ManualMapper mapper, PlatformTransactionManager transactionManager) {
    this.mapper = Objects.requireNonNull(mapper, "business MyBatis mapper");
    this.transactionManager = Objects.requireNonNull(transactionManager, "business transaction manager");
  }
}
