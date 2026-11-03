package com.stratmatrix.planning;

import static org.assertj.core.api.Assertions.assertThat;
import com.stratmatrix.standalone.*;
import com.stratmatrix.planning.adapter.legacy.*;
import com.stratmatrix.planning.manual.*;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class InsideEnvironmentBoundaryTest {
  @Test void insideNeverRegistersLocalAdaptersEvenWithAccidentalLocalProfile(){
    new ApplicationContextRunner()
        .withPropertyValues("spring.profiles.active=inside,local", "planning.manual.enabled=true",
            "planning.local-pulse.enabled=true","planning.legacy.enabled=true")
        .withUserConfiguration(LocalManualBusinessConfiguration.class,LocalExecutionConfiguration.class,
            LegacyPythonConfiguration.class,LegacyPageController.class)
        .run(context->{
          assertThat(context).hasNotFailed();
          assertThat(context).doesNotHaveBean(LocalJobPulse.class);
          assertThat(context).doesNotHaveBean(LegacyPageController.class);
          assertThat(context).doesNotHaveBean(javax.sql.DataSource.class);
        });
  }
  @Test void missingHostDatabaseDoesNotFallBackToTheDevelopmentDatabase(){
    new ApplicationContextRunner().withPropertyValues("spring.profiles.active=inside", "planning.manual.enabled=true")
        .withUserConfiguration(ManualModuleConfiguration.class)
        .run(context->{
          assertThat(context).hasFailed();
          assertThat(context.getStartupFailure()).hasMessageContaining("ManualDatabase");
        });
  }
}
