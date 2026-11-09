package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ConfigReleaseMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.BusinessTransactions;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration("xiangliangBusinessPlanningConfigModule")
@ConditionalOnProperty(name = "planning.business-config.enabled", havingValue = "true")
public class BusinessPlanningConfigModule {
  @Bean(name="xiangliangBusinessPlanningConfigService")
  public BusinessPlanningConfigService businessPlanningConfigService(
      BusinessConfigDatabase database, ConfigReleaseMapper releases, BusinessTransactions transactions) {
    return new BusinessPlanningConfigService(
        database.mapper, transactions, releases);
  }

  @Bean(name="xiangliangConfigReleaseService")
  @ConditionalOnProperty(name = "planning.config-release.enabled", havingValue = "true")
  public ConfigReleaseService configReleaseService(
      ConfigReleaseMapper releases,
      BusinessPlanningConfigService business,
      BusinessConfigDatabase database,
      AlgorithmConfigPort algorithm, BusinessTransactions transactions) {
    return new ConfigReleaseService(releases, business, database, algorithm, transactions);
  }
}
