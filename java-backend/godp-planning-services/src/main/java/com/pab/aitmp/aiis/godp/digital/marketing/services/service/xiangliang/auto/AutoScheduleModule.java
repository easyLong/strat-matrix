package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.auto;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.AutoScheduleMapper;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AutoSchedulePort;

import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigService;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualRepository;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration("xiangliangAutoScheduleModule")
@ConditionalOnProperty(name = "planning.auto-schedule.enabled", havingValue = "true")
public class AutoScheduleModule {
  @Bean(name="xiangliangAutoResultCommitService")
  public AutoResultCommitService autoResultCommitService(
      AutoScheduleMapper mapper, ManualRepository results) {
    return new AutoResultCommitService(mapper, results);
  }

  @Bean(name="xiangliangAutoScheduleService")
  public AutoScheduleService autoScheduleService(
      BusinessPlanningConfigService config,
      AutoScheduleMapper mapper,
      AutoSchedulePort algorithm,
      AutoResultCommitService commit) {
    return new AutoScheduleService(config, mapper, algorithm, commit);
  }
}
