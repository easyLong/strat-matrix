package com.pab.aitmp.aiis.godp.planning.server.config;

import com.pab.aitmp.aiis.godp.planning.api.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.planning.api.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import com.pab.aitmp.aiis.godp.planning.api.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.planning.api.port.SourceFacts;
import com.pab.aitmp.aiis.godp.planning.client.config.PythonProperties;
import com.pab.aitmp.aiis.godp.planning.api.port.PythonRuntimeSettings;
import com.pab.aitmp.aiis.godp.planning.entity.vo.req.PythonEndpoint;
import com.pab.aitmp.aiis.godp.planning.client.python.AlgorithmConfigPythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.AutoSchedulePythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.ManualComputePythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.PythonClient;
import com.pab.aitmp.aiis.godp.planning.client.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.planning.server.controller.BusinessPlanningConfigController;
import com.pab.aitmp.aiis.godp.planning.server.controller.ConfigReleaseController;
import com.pab.aitmp.aiis.godp.planning.server.controller.ManualPlanningController;
import com.pab.aitmp.aiis.godp.planning.server.controller.PlanningHealthController;
import com.pab.aitmp.aiis.godp.planning.server.controller.SourceFactsController;
import com.pab.aitmp.aiis.godp.planning.server.controller.TagTaxonomyController;
import com.pab.aitmp.aiis.godp.planning.server.web.PlanningApiErrors;
import com.pab.aitmp.aiis.godp.planning.server.web.PlanningApiResponseAdvice;
import com.pab.aitmp.aiis.godp.planning.services.auto.AutoScheduleMapper;
import com.pab.aitmp.aiis.godp.planning.services.auto.AutoScheduleModule;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessConfigDatabase;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.planning.services.config.BusinessPlanningConfigModule;
import com.pab.aitmp.aiis.godp.planning.services.config.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentCompletionModule;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentFactsAdapter;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentFlowModule;
import com.pab.aitmp.aiis.godp.planning.services.content.ContentObservations;
import com.pab.aitmp.aiis.godp.planning.services.content.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualMapper;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualModuleConfiguration;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualNewInstallTransition;
import com.pab.aitmp.aiis.godp.planning.services.query.PlanningQueryMapper;
import com.pab.aitmp.aiis.godp.planning.services.query.PlanningReadModule;
import com.pab.aitmp.aiis.godp.planning.services.source.SourceCatalogAdapter;
import com.pab.aitmp.aiis.godp.planning.services.tasks.PlanningTaskModule;

import java.net.URI;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.client.RestTemplate;

/** Import in the existing host; supply named sessions/transactions/HTTP and three host ports. */
@Configuration
@Profile("inside")
@ConditionalOnProperty(name = "planning.host.enabled", havingValue = "true")
@EnableConfigurationProperties(PythonProperties.class)
@Import({
  ManualModuleConfiguration.class,
  BusinessPlanningConfigModule.class,
  AutoScheduleModule.class,
  ContentCompletionModule.class,
  ContentFlowModule.class,
  PlanningReadModule.class,
  PlanningTaskModule.class,
  ManualPlanningController.class,
  ConfigReleaseController.class,
  BusinessPlanningConfigController.class,
  TagTaxonomyController.class,
  PlanningHealthController.class,
  PlanningApiErrors.class,
  PlanningApiResponseAdvice.class,
  SourceFactsController.class,
  HostWebConfiguration.class
})
public class PlanningHostConfiguration {
  @Bean public org.springframework.beans.factory.InitializingBean bankSourceStartupCheck(SourceFacts facts) {
    return () -> {
      if (facts instanceof com.pab.aitmp.aiis.godp.planning.services.source.bank.BankSourceFacts)
        ((com.pab.aitmp.aiis.godp.planning.services.source.bank.BankSourceFacts) facts).verifyReady();
    };
  }
  @Bean
  public PythonClient planningPythonClient(
      PythonProperties p, @Qualifier("planningPythonHttp") RestTemplate http,
      org.springframework.beans.factory.ObjectProvider<PythonRuntimeSettings> providers) {
    PythonRuntimeSettings settings = providers.getIfAvailable(() -> () -> new PythonEndpoint(
        URI.create(java.util.Objects.requireNonNull(p.getBaseUrl(), "planning.python.base-url")), p.getToken()));
    if (!settings.current().configured())
      throw new IllegalStateException("请配置planning.python.base-url及planning.python.token");
    return new PythonClient(settings, http);
  }

  @Bean
  public ManualMapper manualMapper(@Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ManualMapper.class);
  }

  @Bean
  public BusinessPlanningConfigMapper businessPlanningConfigMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(BusinessPlanningConfigMapper.class);
  }

  @Bean
  public ConfigReleaseMapper configReleaseMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ConfigReleaseMapper.class);
  }

  @Bean
  public AutoScheduleMapper autoScheduleMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(AutoScheduleMapper.class);
  }

  @Bean
  public PlanningQueryMapper planningQueryMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(PlanningQueryMapper.class);
  }

  @Bean
  public SlotCompletionMapper slotCompletionMapper(
      @Qualifier("planningBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(SlotCompletionMapper.class);
  }

  @Bean
  public BusinessConfigDatabase businessConfigDatabase(
      BusinessPlanningConfigMapper mapper,
      @Qualifier("planningBusinessTransactions") PlatformTransactionManager tx) {
    return new BusinessConfigDatabase(mapper, tx);
  }

  @Bean
  public AlgorithmConfigPort algorithmConfigPort(PythonClient python) {
    return new AlgorithmConfigPythonClient(python);
  }

  @Bean
  public AutoSchedulePort autoSchedulePort(PythonClient python) {
    return new AutoSchedulePythonClient(python);
  }

  @Bean
  public ManualPorts.Computer manualComputer(PythonClient python) {
    return new ManualComputePythonClient(python);
  }

  @Bean
  public PythonExecutionClient pythonExecutionClient(PythonClient python) {
    return new PythonExecutionClient(python);
  }

  @Bean
  public ManualPorts.Source sourceCatalog(SourceFacts facts, PythonClient python) {
    return new SourceCatalogAdapter(facts, new CatalogProjectionPythonClient(python));
  }

  @Bean
  public PlanningContentPort planningContent(SourceFacts facts) {
    return new ContentFactsAdapter(facts);
  }

  @Bean
  public ManualPorts.ContentStatusSource contentStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::content;
  }

  @Bean
  public ManualPorts.MarketingStatusSource marketingStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::marketing;
  }

  @Bean
  public ManualPorts.Transition planningHistory() {
    return new ManualNewInstallTransition();
  }
}
