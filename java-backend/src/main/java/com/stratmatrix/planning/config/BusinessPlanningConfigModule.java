package com.stratmatrix.planning.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "planning.business-config.enabled", havingValue = "true")
public class BusinessPlanningConfigModule {
  @Bean
  public BusinessPlanningConfigService businessPlanningConfigService(
      BusinessConfigDatabase database, ConfigReleaseMapper releases) {
    return new BusinessPlanningConfigService(
        database.mapper, database.transactionManager, releases);
  }

  @Bean
  @ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
  public ConfigReleaseService configReleaseService(
      ConfigReleaseMapper releases,
      BusinessPlanningConfigService business,
      BusinessConfigDatabase database,
      AlgorithmConfigPort algorithm) {
    return new ConfigReleaseService(releases, business, database, algorithm);
  }
}
