package com.pab.aitmp.aiis.godp.planning.services.config;

import com.pab.aitmp.aiis.godp.planning.api.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.planning.api.port.BusinessTransactions;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "planning.business-config.enabled", havingValue = "true")
public class BusinessPlanningConfigModule {
  @Bean
  public BusinessPlanningConfigService businessPlanningConfigService(
      BusinessConfigDatabase database, ConfigReleaseMapper releases, BusinessTransactions transactions) {
    return new BusinessPlanningConfigService(
        database.mapper, transactions, releases);
  }

  @Bean
  @ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
  public ConfigReleaseService configReleaseService(
      ConfigReleaseMapper releases,
      BusinessPlanningConfigService business,
      BusinessConfigDatabase database,
      AlgorithmConfigPort algorithm, BusinessTransactions transactions) {
    return new ConfigReleaseService(releases, business, database, algorithm, transactions);
  }
}
