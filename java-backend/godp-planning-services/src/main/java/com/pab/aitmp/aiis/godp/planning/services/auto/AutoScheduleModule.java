package com.pab.aitmp.aiis.godp.planning.services.auto;

import com.pab.aitmp.aiis.godp.planning.api.port.AutoSchedulePort;

import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualRepository;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "planning.auto-schedule.enabled", havingValue = "true")
public class AutoScheduleModule {
  @Bean
  public AutoResultCommitService autoResultCommitService(
      AutoScheduleMapper mapper, ManualRepository results) {
    return new AutoResultCommitService(mapper, results);
  }

  @Bean
  public AutoScheduleService autoScheduleService(
      BusinessPlanningConfigService config,
      AutoScheduleMapper mapper,
      AutoSchedulePort algorithm,
      AutoResultCommitService commit) {
    return new AutoScheduleService(config, mapper, algorithm, commit);
  }
}
