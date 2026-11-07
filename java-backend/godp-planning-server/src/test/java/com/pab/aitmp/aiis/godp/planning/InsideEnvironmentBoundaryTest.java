package com.pab.aitmp.aiis.godp.planning;

import com.pab.aitmp.aiis.godp.planning.server.dev.*;
import com.pab.aitmp.aiis.godp.planning.server.dev.legacy.*;
import com.pab.aitmp.aiis.godp.planning.services.manual.*;

import com.pab.aitmp.aiis.godp.planning.server.dev.LocalExecutionConfiguration;
import com.pab.aitmp.aiis.godp.planning.server.dev.LocalJobPulse;
import com.pab.aitmp.aiis.godp.planning.server.dev.LocalManualBusinessConfiguration;
import com.pab.aitmp.aiis.godp.planning.server.dev.legacy.LegacyPythonConfiguration;
import com.pab.aitmp.aiis.godp.planning.services.manual.ManualModuleConfiguration;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class InsideEnvironmentBoundaryTest {
  @Test void insideNeverRegistersLocalAdaptersEvenWithAccidentalLocalProfile(){
    new ApplicationContextRunner()
        .withPropertyValues("spring.profiles.active=inside,local", "planning.manual.enabled=true",
            "planning.local-pulse.enabled=true","planning.legacy.enabled=true")
        .withUserConfiguration(LocalManualBusinessConfiguration.class,LocalExecutionConfiguration.class,
            LegacyPythonConfiguration.class)
        .run(context->{
          assertThat(context).hasNotFailed();
          assertThat(context).doesNotHaveBean(LocalJobPulse.class);
          assertThat(context).doesNotHaveBean(javax.sql.DataSource.class);
        });
  }
  @Test void missingHostDatabaseDoesNotFallBackToTheDevelopmentDatabase(){
    new ApplicationContextRunner().withPropertyValues("spring.profiles.active=inside", "planning.manual.enabled=true")
        .withUserConfiguration(ManualModuleConfiguration.class)
        .run(context->{
          assertThat(context).hasFailed();
          assertThat(context.getStartupFailure()).hasMessageContaining("ManualMapper");
        });
  }
}
