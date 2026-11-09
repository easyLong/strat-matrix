package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.Import;

/** 行外启动壳；驻场复制业务模块时不复制此启动类。 */
@SpringBootApplication(scanBasePackages = {
    "com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang",
    "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.controller",
    "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.web",
    "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config",
    "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.local",
    "com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.legacy"
}, exclude = DataSourceAutoConfiguration.class)
@Import({LocalExecutionConfiguration.class, LocalManualBusinessConfiguration.class,
    ServiceHealthController.class})
public class PlanningDevelopmentApplication {
    public static void main(String[] args) {
        SpringApplication.run(PlanningDevelopmentApplication.class, args);
    }
}
