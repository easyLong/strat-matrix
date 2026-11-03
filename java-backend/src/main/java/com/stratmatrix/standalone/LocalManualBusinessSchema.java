package com.stratmatrix.standalone;

import javax.sql.DataSource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

/**
 * Local development DDL only. The bank host applies the SQL through its database release process.
 */
public final class LocalManualBusinessSchema {
  private LocalManualBusinessSchema() {}

  public static void initialize(DataSource businessDataSource) {
    ResourceDatabasePopulator schema =
        new ResourceDatabasePopulator(
            new ClassPathResource("db/manual-business.sql"),
            new ClassPathResource("db/business-planning-config.sql"),
            new ClassPathResource("db/auto-planning-business.sql"),
            new ClassPathResource("db/slot-completion.sql"));
    schema.setSqlScriptEncoding("UTF-8");
    schema.setContinueOnError(false);
    schema.execute(businessDataSource);
  }
}
