package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AlgorithmConfigPort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.AutoSchedulePort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.ManualPorts;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PlanningContentPort;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.SourceFacts;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.config.PythonProperties;
import com.pab.aitmp.aiis.godp.digital.marketing.api.xiangliang.port.PythonRuntimeSettings;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req.PythonEndpoint;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.AlgorithmConfigPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.AutoSchedulePythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.CatalogProjectionPythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.ManualComputePythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonClient;
import com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python.PythonExecutionClient;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.BusinessPlanningConfigController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.ConfigReleaseController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.ManualPlanningController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.PlanningHealthController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.SourceFactsController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller.TagTaxonomyController;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web.PlanningApiErrors;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web.PlanningApiResponseAdvice;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.AutoScheduleMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.auto.AutoScheduleModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessConfigDatabase;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.BusinessPlanningConfigMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.config.BusinessPlanningConfigModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ConfigReleaseMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentCompletionModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentFactsAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentFlowModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.content.ContentObservations;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.SlotCompletionMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualModuleConfiguration;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual.ManualNewInstallTransition;
import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.PlanningQueryMapper;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.query.PlanningReadModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.SourceCatalogAdapter;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.tasks.PlanningTaskModule;
import com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.persistence.BusinessMapperSupport;

import java.net.URI;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.client.RestTemplate;

/** Import in the existing host; supply named sessions/transactions/HTTP and three host ports. */
@Configuration("xiangliangPlanningHostConfiguration")
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
  @Bean(name = "xiangliangPersistenceStartupCheck")
  public org.springframework.beans.factory.InitializingBean persistenceStartupCheck(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate sessions,
      @Qualifier("xiangliangBusinessTransactions") PlatformTransactionManager transactions) {
    return () -> BusinessMapperSupport.verify(sessions, transactions);
  }

  @Bean(name="xiangliangBankSourceStartupCheck") public org.springframework.beans.factory.InitializingBean bankSourceStartupCheck(SourceFacts facts) {
    return () -> {
      if (facts instanceof com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceFacts)
        ((com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank.BankSourceFacts) facts).verifyReady();
    };
  }
  @Bean(name="xiangliangPlanningPythonClient")
  public PythonClient planningPythonClient(
      PythonProperties p, @Qualifier("xiangliangPythonHttp") RestTemplate http,
      org.springframework.beans.factory.ObjectProvider<PythonRuntimeSettings> providers) {
    PythonRuntimeSettings settings = providers.getIfAvailable(() -> () -> new PythonEndpoint(
        URI.create(java.util.Objects.requireNonNull(p.getBaseUrl(), "planning.python.base-url")), p.getToken()));
    if (!settings.current().configured())
      throw new IllegalStateException("请配置planning.python.base-url及planning.python.token");
    return new PythonClient(settings, http);
  }

  @Bean(name="xiangliangManualMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public ManualMapper manualMapper(@Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ManualMapper.class);
  }

  @Bean(name="xiangliangBusinessPlanningConfigMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public BusinessPlanningConfigMapper businessPlanningConfigMapper(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(BusinessPlanningConfigMapper.class);
  }

  @Bean(name="xiangliangConfigReleaseMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public ConfigReleaseMapper configReleaseMapper(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(ConfigReleaseMapper.class);
  }

  @Bean(name="xiangliangAutoScheduleMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public AutoScheduleMapper autoScheduleMapper(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(AutoScheduleMapper.class);
  }

  @Bean(name="xiangliangPlanningQueryMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public PlanningQueryMapper planningQueryMapper(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(PlanningQueryMapper.class);
  }

  @Bean(name="xiangliangSlotCompletionMapper")
  @DependsOn("xiangliangPersistenceStartupCheck")
  public SlotCompletionMapper slotCompletionMapper(
      @Qualifier("xiangliangBusinessSessions") SqlSessionTemplate s) {
    return s.getMapper(SlotCompletionMapper.class);
  }

  @Bean(name="xiangliangBusinessConfigDatabase")
  public BusinessConfigDatabase businessConfigDatabase(
      BusinessPlanningConfigMapper mapper,
      @Qualifier("xiangliangBusinessTransactions") PlatformTransactionManager tx) {
    return new BusinessConfigDatabase(mapper, tx);
  }

  @Bean(name="xiangliangAlgorithmConfigPort")
  public AlgorithmConfigPort algorithmConfigPort(PythonClient python) {
    return new AlgorithmConfigPythonClient(python);
  }

  @Bean(name="xiangliangAutoSchedulePort")
  public AutoSchedulePort autoSchedulePort(PythonClient python) {
    return new AutoSchedulePythonClient(python);
  }

  @Bean(name="xiangliangManualComputer")
  public ManualPorts.Computer manualComputer(PythonClient python) {
    return new ManualComputePythonClient(python);
  }

  @Bean(name="xiangliangPythonExecutionClient")
  public PythonExecutionClient pythonExecutionClient(PythonClient python) {
    return new PythonExecutionClient(python);
  }

  @Bean(name="xiangliangSourceCatalog")
  public ManualPorts.Source sourceCatalog(SourceFacts facts, PythonClient python) {
    return new SourceCatalogAdapter(facts, new CatalogProjectionPythonClient(python));
  }

  @Bean(name="xiangliangPlanningContent")
  public PlanningContentPort planningContent(SourceFacts facts) {
    return new ContentFactsAdapter(facts);
  }

  @Bean(name="xiangliangContentStatusSource")
  public ManualPorts.ContentStatusSource contentStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::content;
  }

  @Bean(name="xiangliangMarketingStatusSource")
  public ManualPorts.MarketingStatusSource marketingStatusSource(SourceFacts facts) {
    return new ContentObservations(facts)::marketing;
  }

  @Bean(name="xiangliangPlanningHistory")
  public ManualPorts.Transition planningHistory() {
    return new ManualNewInstallTransition();
  }
}
