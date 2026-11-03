package com.stratmatrix.standalone;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Import;

/** 行外启动壳；驻场复制业务模块时不复制此启动类。 */
@SpringBootApplication(scanBasePackages = "com.stratmatrix.planning", exclude = DataSourceAutoConfiguration.class)
@Import({LocalExecutionConfiguration.class, LocalManualBusinessConfiguration.class,
    ServiceHealthController.class})
public class PlanningDevelopmentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PlanningDevelopmentApplication.class, args);
    }
}
